import os
import sys
import pwd
import traceback
from random import randrange
import socket
import subprocess
import re
import ConfigParser
import socket
import getpass

# logging
import sys
import logging
logger = logging.getLogger( __name__ )
logger.setLevel(logging.WARNING)
logger.propagate = False

formatter = logging.Formatter('[%(asctime)-15s] [hServerProxy] %(message)s')

# create console handler and configure
consoleLog = logging.StreamHandler(sys.stdout)
consoleLog.setLevel(logging.DEBUG)
consoleLog.setFormatter(formatter)

# add handler to logger
logger.addHandler(consoleLog)

# path to bin directory
BINPATH = "{hqpath}/bin".format( hqpath=os.environ['HQPATH'] )
# path to config files
ETCPATH = "{hqpath}/etc".format( hqpath=os.environ['HQPATH'] )

# import hq libraries
from hq.lib.hQSocket import hQSocket
from hq.lib.hQServerDetails import hQServerDetails
import hq.lib.hQUtils as hQUtils

HOMEDIR = os.environ['HOME']
USER = getpass.getuser()

class hQServerProxy(object):
    """! @brief Class for establishing a running Server, such as hq-user-server or hq-exec-server and connect to it"""
    def __init__(self,
                 serverType = '',
                 host = None,
                 logFile = "",
                 verboseMode = False,
                 persistent = False ):
        """! @brief Constructor
        
        @param serverType (string) Type of server. Currently supported are user-server and user-menial-server.
        
        """
        self.user = USER
        self.host = host
        self.serverType = serverType
        self.logFile = logFile
        self.verboseMode = verboseMode
        self.clientSock = None
        self.running = False	# set true if server responsed to ping
        self.started = False	# set true if server has been started
        self.persistent = persistent

        #self.homedir = os.environ['HOME']

        if self.verboseMode:
            logger.setLevel( logging.DEBUG )

        logger.info( 'server proxy for hq-{s}'.format(s=self.serverType) )
        
        # read default config file
        hqConfigFileName = "%s/hq.cfg" % ETCPATH
        
        logger.info( "read config file {f}".format(f=hqConfigFileName) )
        
        if os.path.exists( hqConfigFileName ):
            hqConfig = ConfigParser.ConfigParser()
            hqConfig.read( hqConfigFileName )
        else:
            logger.info( "ERROR: config file {f} could not be found".format( f=hqConfigFileName ) )
            sys.exit(-1)

        # python executable (to start server)
        self.python = hqConfig.get( 'SYSTEM', 'python' )

        # get stored server details
        hqServerDetails = hQServerDetails( self.serverType )
        
        logger.info( "read config file {f} for hq-{serverType}.".format( f=hqServerDetails.cfgFile,
                                                                         serverType=self.serverType) )
        if not self.host:
            # get host from config file or use current host
            self.host = hqServerDetails.get('host', host if host else os.uname()[1])

        # get port from config file or get default port. add 1 to default port for exec-server's
        a = 1 if self.serverType=='exec-server' else 0
        self.port = hqServerDetails.get('port', hQUtils.getDefaultPort( self.user, add=a) )
        

    def run(self):
        """! @brief check if there is a server running on stored port. if not try to invoke one."""
        status = None
        cnt = 0

        logger.info( 'run server' )
        
        # try maximal 5 times to invoke a server
        while cnt<5 and not self.running:
            cnt += 1

            logger.info( "[{i}. attempt] checking server on {h}:{p}. ".format( i=cnt,
                                                                               h=self.host,
                                                                               p=self.port) )

            connStatus = self.connectToServer( cnt )

            if connStatus == 1:
                # Server is running and understands me
                break
            elif connStatus == 2:
                # Server is running but do not understands me
                self.port += 1
            elif connStatus == 3:
                # Server is not running
                ##newHost = os.uname()[1]
                ##
                ### store new host
                ##if newHost != self.host:
                ##    self.host = newHost
                pass

            # try to start a new Server on port in case of status 2 or 3
            status = self.invokeServer( cnt )

    def connect( self ):
        """! @brief just create new socket """

        if not self.clientSock:
            try:
                self.clientSock = hQSocket( host=self.host,
                                            port=self.port,
                                            catchErrors=False )
            except:
                pass

    def isRunning( self ):
        """! @brief check if server is running

        @return (boolean) True|False
        """
        
        connStatus = self.connectToServer( 1 )

        if connStatus == 1:
            # Server is running and understands me
            return True
        elif connStatus == 2:
            # Server is running but do not understands me
            return False
        elif connStatus == 3:
            # Server is not running
            return False
        

    def connectToServer(self, cnt=1):
        """ check for Server
            return: 1 ... Server is running and understands me
                    2 ... Server is running but do not understands me
                    3 ... Server is not running"""

        try:
            lDict = { 'i': cnt,
                      'h': self.host,
                      'p': self.port }
            logger.info( "[{i}. attempt] connecting to server on {h}:{p}.".format( **lDict ) )

            #self.clientSock = hQSocket( host=self.host,
            #                            port=self.port,
            #                            catchErrors=False)

            command = "ping"
            #self.clientSock.send(command)
            self.send( command )
            
            response = self.clientSock.recv()

            self.clientSock.close()
            
            if response == "pong":
                logger.info( "[{i}. attempt] ... server on {h}:{p} is running.".format( **lDict ) )

                self.running = True
                return 1
            else:
                logger.info( "[{i}. attempt] ... server on {h}:{p} is running, but connection failed.".format( **lDict ) )
                logger.info( "[{i}. attempt] ... error: {e}".format(i=cnt, e=response) )

                self.running = False
                return 2

        except socket.error,msg:
            # msg is something like "[Errno 111] Connection refused":
            self.running = False

            logger.info( "[{i}. attempt] ... server on {h}:{p} is NOT running.".format(**lDict) )
            logger.info( "[{i}. attempt] ... error: {e}".format(i=cnt, e=msg) )

            return 3
            
        except AttributeError,msg:
            self.running = False
            
            logger.info( "[{i}. attempt] ... server on {h}:{p} is NOT running.".format(**lDict) )
            logger.info( "[{i}. attempt] ... error: {e}".format(i=cnt, e=msg) )

            return 3
            


    def invokeServer(self, cnt):
        """@brief  invoke server on given host and port

        @return (successful|finished) with 'successful': started server and 'failed': start has failed
        """

        lDict = { 'i': cnt,
                  'h': self.host,
                  'p': self.port }
        logger.info( "[{i}. attempt] invoke server on {h}:{p}. ".format( **lDict ) )

        try:
            runServer = 'hq-'+self.serverType

            com = "ssh -x -a {host} {binpath}/{runServer} -p {port}".format( host = self.host,
                                                                             binpath = BINPATH,
                                                                             runServer = runServer,
                                                                             port = self.port)

            logger.info( "[{i}. attempt] command: {command}".format( i=cnt,
                                                                     command=com) )

            # invoke server as daemon
            sp=subprocess.Popen(com,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
            out,err = sp.communicate()

            if re.search('Address already in use',err):
                logger.info( "[{i}. attempt] ... Address already in use".format(i=cnt) )
                
                self.started = False
                self.running = False
                
                return "failed"
            elif err:
                logger.info( "[{i}. attempt] ... Server error while initiation: {err}".format(i=cnt, err=err) )
                
                self.started = False
                self.running = False
                
                return "failed"
            else:
                self.started = True

                logger.info( "[{i}. attempt] ... Server has been started on {h}:{p}".format( **lDict ) )

                return "successful"

        except socket.error,msg:
            logger.warning( "[{i}. attempt] ... Connection to server on {h}:{p} could not be established".format( **lDict ) )
            
            return "failed"


    def send(self, command):
        logger.info( "send request: {c}".format(c=command) )

        try:
            self.clientSock.send(command)
        except:
            self.clientSock = hQSocket( host=self.host,
                                        port=self.port,
                                        catchErrors=False )
            self.clientSock.send(command)

        logger.info( "... done" )
        
        return True


    def recv(self):
        try:
            recv = self.clientSock.recv()

            recvShort = recv.replace('\n', '\\')[:30]
            logger.info( "response from server: {r}{dots}".format(r=recvShort, dots="..." if len(recv)>30 else "" ) )

            self.close()
            return recv
        except socket.error,msg:
            return msg.message


    def close(self):
        """ close connection

        does it work??
        """

        logger.info( "close connection" )
        
        self.clientSock.shutdown(socket.SHUT_RDWR)
        self.openConnection = False


    def sendAndRecv(self,request):
        """ send request to server and receive response"""
        self.send(request)

        return self.recv()


    def sendAndClose(self,request):
        """ send request to server and close connection"""
        try:
            self.send(request)
            self.close()
        except socket.error,msg:
            self.openConnection = False
            sys.stderr.write("SOCKET ERROR: % s\n" % msg)
        except:
            self.openConnection = False
            sys.stderr.write("UNKNOWN ERROR: % s\n" % sys.exc_info()[0])
            traceback.print_exc(file=sys.stderr)
    
    
    ##def sendAndRecvAndClose(self,request):
    ##    """ send request to server, receive response and close connection"""
    ##    try:
    ##        self.send(request)
    ##        response = self.recv()
    ##        self.close()
    ##        return response
    ##    except socket.error,msg:
    ##        self.openConnection = False
    ##        sys.stderr.write("SOCKET ERROR: % s\n" % msg)
    ##    except:
    ##        self.openConnection = False
    ##        sys.stderr.write("UNKNOWN ERROR: % s\n" % sys.exc_info()[0])
    ##        traceback.print_exc(file=sys.stderr)

    def shutdown( self ):
        """! brief shutdown server """

        command = "shutdown"
        self.clientSock = hQSocket( host=self.host,
                                    port=self.port,
                                    catchErrors=False )
        
        self.clientSock.send(command)
        
        self.clientSock = hQSocket( host=self.host,
                                    port=self.port,
                                    catchErrors=False )
        
        self.clientSock.send("ping")

        return "done"
            
        
