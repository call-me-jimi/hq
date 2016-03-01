import os
import pwd
import sys
from datetime import datetime
import time
import threading
import ConfigParser
import SocketServer
import traceback
import re

# import hq libraries
from hq.lib.hQSocket import hQSocket
from hq.lib.hQCommand import hQCommand
from hq.lib.hQLogger import hQLogger, wrapLogger
from hq.lib.hQDBConnection import hQDBConnection
from hq.lib.hQServerDetails import hQServerDetails
from hq.lib.daemon import Daemon
import hq.lib.hQUtils as hQUtils
import hq.lib.hQDatabase as db

# path to config files
ETCPATH = "{hqpath}/etc".format( hqpath=os.environ['HQPATH'] )

PRINT_STATUS_COUNTER=5
SERVER_TIMEOUT=3

class hQBaseServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer, Daemon, object):
    # This means the main server will not do the equivalent of a
    # pthread_join() on the new threads.  With this set, Ctrl-C will
    # kill the server reliably.
    daemon_threads = True

    # By setting this it is allowed for the server to re-bind to the address by
    # setting SO_REUSEADDR, meaning you don't have to wait for
    # timeouts when you kill the server and the sockets don't get
    # closed down correctly.
    allow_reuse_address = True
    request_queue_size = 30

    # set maximum number of children. actually has to be adjust according to number of cpu's
    max_children=64

    server_type ='hq-base-server'

    def __init__( self,
                  port,
                  handler,
                  processor ):

        self.server_id = str( time.time() )
        
        Daemon.__init__(self,'/tmp/{serverType}.{serverID}.pid'.format( serverType=self.server_type,
                                                                        serverID=self.server_id) )
        
        t = datetime.now()
        self.startTime = str( t )
        
        self.mainThread = threading.currentThread()
        self.mainThread.started = t
        
        self.host = os.uname()[1]
        self.port = port

        self.processor = processor

        self.logger = hQLogger()
    
        # initialize socket server
        SocketServer.TCPServer.__init__(self, (self.host,self.port), handler)

        # read hQ config
        self.config = ConfigParser.ConfigParser()
        self.config.read( '{etcpath}/hq.cfg'.format(etcpath=ETCPATH) )

        # set server time out (time after which self.handle_request returns without a request)
        self.timeout=SERVER_TIMEOUT
        
        # store some database ids in dict
        self.init_database_ids()
        
        self.loops = {}

        self.shutdown_server_event = threading.Event()
        self.print_status_counter = 0


    def run(self):
        """!@brief Start up a server
        
        Each time a new request comes in it will be handled by a RequestHandler class
        """

        # get pid of daemon process
        try:
            with open(self.pidfile) as f:
                self.pid = f.readline().strip()
        except:
            # process has probably not been started as daemon
            self.pid = os.getpid()
            #with open(self.pidfile,'w+') as f:
            #    f.write("%s\n" % self.pid)
                
        try:
            self.logger.write( '{st} has been started on {h}:{p}'.format( st = self.server_type.upper(),
                                                                          h = self.host,
                                                                          p = self.port ),
                               logCategory='status')

            self.store_details()
            self.start_loops()
            
            self.serve_forever()
        except KeyboardInterrupt:
            sys.exit(0)


    def store_details( self ):
        """! extends store details about running server """
        
        # create hQServerDetails instance
        hqServerDetails = hQServerDetails(self.server_type)
        # write host and port to file <varpath>/hq.server.cfg
        hqServerDetails.save([ ('host', self.host),
                               ('port', self.port),
                               ('id', self.server_id),
                               ('pid', self.pid),
                               ('started', self.startTime )
                               ])


    def init_database_ids( self ):
        """! @brief save some database ids in self.database_ids
        """

        con = hQDBConnection()
        
        self.database_ids = dict( con.query( db.JobStatus.name,
                                             db.JobStatus.id ).all() )


    def serve_forever(self):
        """!@brief overwrites serve_forever of SocketServer.TCPServer"""
    
        # set threads as daemon threads
        # the threading doc says:
        #    A thread can be flagged as a "daemon thread". The significance of this flag is that the
        #    entire Python program exits when only daemon threads are left. The initial value is
        #    inherited from the creating thread. The flag can be set through the daemon property.
    
        
        # print status to stdout
        self.print_status()

        self.logger.write( 'ready to handle requests'.format( st = self.server_type ),
                           logCategory='status')
        

        while not self.shutdown_server_event.is_set():
            self.handle_request()

            self.after_request_processing()

        self.shutdown_server()


    def after_request_processing( self ):
        """! @brief is executed after a request came in

        can be overwritten by child class
        """
        pass


    def run_loop( self, name, **kwargs ):
        """! @brief generic function for periodically executing a function

        """

        while True:
            loop = self.loops[ name ]
            
            interval = loop[ 'interval' ]
            fct = loop[ 'fct' ]
            
            # wait a little bit
            time.sleep( interval )

            try:
                if not loop[ 'is_running' ].is_set():
                    # set lock
                    loop[ 'is_running' ].set()
                    # run function
                    fct( **kwargs )
                    # release lock
                    loop[ 'is_running' ].clear()
                else:
                    # skip while the previous function is still executing
                    self.logger.write( 'loop {p} is still running'.format(p=name) )
                    continue
            except:
                # something went wrong
                # release lock
                self.logger.write( 'loop {p} had an exception'.format(p=name) )
                loop[ 'is_running' ].clear()

            
    def start_loops( self ):
        """! @brief start loops """

        # iterate over all loop functions in self.loops and start them in an own thread,
        # respectively
        for loopName,loop in self.loops.iteritems():
            # collect arguments for self.run_loop
            kwargs = loop.get( 'kwargs', {} )

            loopKwargs = kwargs.copy()
            loopKwargs.update( { 'name': loopName } )

            # add an event lock to the loop as an idicator of beeing running
            self.loops[ loopName ][ 'is_running' ] = threading.Event()
                               
            l = threading.Thread( target=self.run_loop, kwargs=loopKwargs )
            l.setDaemon( True )
            l.setName( "(loop) {name}".format(name=loopName) )
            l.started = datetime.now()
            l.start()

            self.logger.write( "started loop '{name}'".format(name=loopName),
                               logCategory='init' )

                               
    def print_status( self, *args, **kwargs ):
        """! @brief print status of server to stdout

        has to be overwritten by the child
        """
        pass

    
    def shutdown_server( self ):
        """! @brief shutdown server """
        self.logger.write( "server is about to shutdown.",
                           logCategory='system')
        
        # wait until all threads have been finished
        
        
        self.logger.write( "shutdown.",
                           logCategory='system')
        
        
# RequestHandler handles an incoming request.
class hQBaseServerHandler(SocketServer.BaseRequestHandler,object):
    def __init__(self, request, clientAddress, server):
        self.request = request
        self.requestHost, self.requestPort = self.request.getpeername()
        self.srv = server
        self.currThread = threading.currentThread()
        self.ident = self.currThread.ident
        
        # add new attribute to Thread object
        self.currThread.started = datetime.now()

        # wrap self.src.logger
        # call self.writeLog with message and logCategory
        self.writeLog = wrapLogger( self.srv.logger, prefix='[{id}] '.format(id=self.ident) )

        SocketServer.BaseRequestHandler.__init__(self, self.request, clientAddress, self.srv)


    def handle(self):
        if self.srv.shutdown_server_event.is_set():
            # do not process event while server ist shutting down
            return
        
        self.srv.print_status_counter += 1
        
        # create a hQSocket-instance
        requestSocket = hQSocket( sock = self.request, 
                                  serverSideSSLConn = True,
                                  catchErrors = False,
                                  timeout = 10 )
        try:
            receivedStr = requestSocket.recv()
        except socket.timeout:
            self.writeLog( "Timeout while reading from socket {h}:{p}. Skip".format( h = self.requestHost,
                                                                                   p = self.requestPort),
                         logCategory='warning' )
            return

        #requestStrShort = "{r1}{dots}{r2}".format( r1=receivedStr[:20] if len(receivedStr)>40 else receivedStr,
        #                                           dots="   " if len(receivedStr)>80 else "",
        #                                           r2=receivedStr[-20:] if len(receivedStr)>40 else "" )
        requestStrShort = "{r1}{dots}".format( r1=receivedStr[:30] if len(receivedStr)>30 else receivedStr,
                                               dots="..." if len(receivedStr)>30 else ""
                                               )
        
        # add new attribute to Thread object
        self.currThread.command = receivedStr
        self.currThread.command_short = requestStrShort
        
        self.writeLog( "NEW REQUEST FROM {h}:{p}: {s}".format( s = requestStrShort,
                                                             h = self.requestHost,
                                                             p = self.requestPort ),
                     logCategory='request_processing' )

        t1 = datetime.now()

        # process request
        try:
            self.srv.processor.process(receivedStr, requestSocket, self.writeLog, self.srv)
        except:
            # processing failed
            tb = sys.exc_info()

            self.writeLog('Error while processing request from {h}:{p}!\n'.format(h=self.requestHost,
                                                                                p=self.requestPort),
                        logCategory='error' )

            traceback.print_exception(*tb,file=sys.stderr)

            requestSocket.send("Error while processing request!\n%s" %  tb[1])

        t2 = datetime.now()

        self.writeLog( "REQUEST PROCESSED IN {dt}s.".format(dt=str(t2-t1) ),
                     logCategory='request_processing')
            

    def finish(self):
        """! @brief excute functions after request has been processed
        """
        if self.srv.shutdown_server_event.is_set():
            # do not process event while server ist shutting down
            return
        
        if self.srv.print_status_counter>=PRINT_STATUS_COUNTER:
            self.srv.print_status_counter = 0
            
            self.srv.print_status( short=True )
            
        super(hQBaseServerHandler, self).finish()
    


# This class is used to process the commands
class hQBaseRequestProcessor(object):
    def __init__( self ):
        ############
        # define commands
        ############
        
        self.commands = {}	# {<COMMAND>: hQCommand, ...}

        
        self.commands["HELP"] = hQCommand( name = "help",
                                           regExp = "^help$",
                                           help = "return help",
                                           fct = self.process_help )
        self.commands["PING"] = hQCommand( name = "ping",
                                           regExp = '^ping$',
                                           help = "return 'pong'",
                                           fct = self.process_ping )
        self.commands["INFO"] = hQCommand( name = "info",
                                           regExp = "^info$",
                                           help = "return some information about server",
                                           fct = self.process_details )
        self.commands["STATUS"] = hQCommand( name = "status",
                                             regExp = "^status$",
                                             help = "print status of server",
                                             fct = self.process_status )
        self.commands["SHUTDOWN"] = hQCommand( name = "shutdown",
                                             regExp = "^shutdown$",
                                             help = "shutdown server",
                                             fct = self.process_shutdown )
        self.commands["LSTHREADS"] = hQCommand( name = "lsthreads",
                                                regExp = "^lsthreads$",
                                                help = "return list of active threads with [start time] [thread id] [thread name] [shorted command]",
                                                fct = self.process_lsthreads )
        self.commands["LSTHREAD"] = hQCommand( name = "lsthread",
                                               regExp = "^lsthread:(.*)",
                                               arguments = ['thread_id'],
                                               help = "return details of thread with specified id (see lsthread)",
                                               fct = self.process_lsthread )
        self.commands["LSLOGGER"] = hQCommand( name = "lslogger",
                                               regExp = "^lslogger$",
                                               help = "return logger setting",
                                               fct = self.process_lslogger )
        self.commands["ACTIVATELOGGER"] = hQCommand( name = "activatelogger",
                                                     regExp = "^activatelogger:(.*)",
                                                     arguments = ["logger"],
                                                     help = "activate logger",
                                                     fct = self.process_activatelogger )
        self.commands["DEACTIVATELOGGER"] = hQCommand( name = "deactivatelogger",
                                                       regExp = "^deactivatelogger:(.*)",
                                                       arguments = ["logger"],
                                                       help = "deactivate logger",
                                                       fct = self.process_deactivatelogger )
        self.commands["LSLOOP"] = hQCommand( name = "lsloops",
                                              regExp = "^lsloops$",
                                              help = "return list of loops",
                                              fct = self.process_lsloops )
        self.commands["SETLOOPINTERVAL"] = hQCommand( name = "setloopinterval",
                                              regExp = "^setloopinterval:(.*):(.*)$",
                                              arguments = ["loop_key","interval"],
                                              help = "set interval of loop with provided key (check lsloops) to interval in seconds",
                                              fct = self.process_updateloop )
        self.commands["SLEEP"] = hQCommand( name = "sleep",
                                            regExp = "^sleep:(.*)",
                                            arguments = ['time_in_secs'],
                                            help = "just sleep",
                                            fct = self.process_sleep )

        ## help fill be set with the first call of self.process
        ##self.help = {}

    def process(self, requestStr, request, logger, server):
        """! @brief Process a requestStr"""
        self.writeLog = logger
        self.server = server

        #if not self.help:
        #    # generate dictinary with regular regression for each command
        #    self.help = { key: re.compile('^help {cmd_name}$'.format(cmd_name=cmd.name)) for key,cmd in self.commands.iteritems() }

        m = re.match( 'help ?(.*)', requestStr )
        if m:
            command = m.group(1)
            
            if command=="":
                # no command has been given
                # return all commands
                help = []
                help.append( "Known commands:" )

                # iterate over all commands defined in self.commands
                help.extend( hQUtils.renderHelp( sorted(self.commands.keys()), self.commands ) )

                request.send( '\n'.join( help ) )
            else:
                try:
                    key = next( key for key,c in self.commands.iteritems() if command==c.name )

                    cmd = self.commands[ key ]

                    response = [ "help for '"+cmd.name+"':" ]
                    response.append( "--------------------" )
                    response.append( "full command: {c}".format(c=cmd.get_command_str() ) )
                    response.append( "" )
                    response.append( cmd.get_fullhelp() )

                    request.send( '\n'.join( response ) )
                except StopIteration:
                    matching_commands = [ c.name for key,c in self.commands.iteritems() if c.name.startswith( command ) ]

                    if matching_commands:
                        response = []
                        response.append( "command '" + command + "' is unknown!" )
                        response.append( "" )
                        response.append( "similar commands:" )
                        for c in matching_commands:
                            response.append( "  "  + c )

                        request.send( '\n'.join( response ) )
                    else:
                        request.send( 'no matching command.' )
        else:
            # (2) find matching command and execute associate function
            try:
                cmd = next( cmd for cmd_str,cmd in self.commands.iteritems() if cmd.match( requestStr ) )
            except:
                self.writeLog("unknown command.", logCategory='request_processing')

                request.send("what do you want?")
                return

            # process request
            try:
                self._call_fct( cmd, requestStr, request )
            except:
                self.writeLog("error while processing request.", logCategory='request_processing')
                print traceback.print_exc()

                request.send("Request could not be processed.")
                return
                

            
    def _call_fct( self, cmd, requestStr, request ):
        """! @brief call function with right arguments"""
        cmd.fct( request, **dict( zip(cmd.arguments,cmd.groups(requestStr)) ) )

        
    def process_help( self, request ):
        """! @brief process 'help' command
        """
        help = []
        help.append( "Known commands:" )
        
        # iterate over all commands defined in self.commands
        help.extend( hQUtils.renderHelp( sorted(self.commands.keys()), self.commands ) )
            
        request.send( '\n'.join( help ) )


    def process_ping( self, request ):
        """! @brief process 'ping' command
        """
        request.send("pong")

        
    def process_details( self, request ):
        """! @brief process 'details' command
        """

        details  = 'Details about {name}\n'.format( name=self.server.server_type )
        details += '----------------------\n'
        details += "{s:>20} : {value}\n".format(s="host", value=self.server.host )
        details += "{s:>20} : {value}\n".format(s="port", value=self.server.port )
        details += "{s:>20} : {value}\n".format(s="started", value=self.server.startTime )
        details += "{s:>20} : {value}\n".format(s="pid", value=self.server.pid )
        
        request.send( details )


    def process_status( self, request ):
        """! @brief process 'lsloops' command
        """
        
        status = self.server.print_status( returnString=True )
            
        request.send( status )

        
    def process_shutdown( self, request ):
        """! @brief process 'shutdown' command
        """

        self.server.shutdown_server_event.set()
        
        
    def process_sleep( self, request, **kwargs ):
        """! @brief just sleep"""

        t = int( kwargs['time_in_secs'] )
        time.sleep( t )

        
    def process_lsthreads( self, request ):
        """! @brief process 'lsthreads' command
        """

        def _formatDict( idx, t):
            return { 'idx': idx,
                     'id': t.ident,
                     'cmd': ' - '+t.command_short if hasattr(t,'command_short') else '' ,
                     'name': t.getName() }
        
        threadList = [ "{idx:3d}. [{id}] {name}{cmd}".format( **_formatDict(idx,t) ) for idx,t in enumerate(threading.enumerate() ) ]
        request.send( '\n'.join( threadList ) )
            

    def process_lsthread( self, request, ident ):
        """! @brief process 'lsthreads' command
        """
        try:
            ident = int( ident )
        except:
            request.send("invalid key.")
            return

        try:
            thread = next( t for t in threading.enumerate() if t.ident==ident )
        except StopIteration:
            # not found
            request.send("invalid key.")
            return

        response = "Thread details\n"
        response += "----------------------\n"
        response += "{s:>20} : {value}\n".format(s="id", value=thread.ident )
        response += "{s:>20} : {value}\n".format(s="name", value=thread.getName() )
        try:
            response += "{s:>20} : {value}\n".format(s="command", value=thread.command )
        except:
            pass
        try:
            response += "{s:>20} : {value}\n".format(s="started at", value=str(thread.started) )
            response += "{s:>20} : {value}\n".format(s="running since", value=str(datetime.now()-thread.started) )
        except:
            pass

        request.send( response )

    def process_lsloops( self, request ):
        """! @brief process 'lsloops' command
        """

        def _formatDict( idx, loopKey):
            loop = self.server.loops[ loopKey ]
            return { 'idx': idx,
                     'name': loopKey,
                     'interval': loop['interval'],
                     'description': loop['description'] }
        
        loopList = [ "{idx:2d}. [every {interval}s] {name} - {description}".format( **_formatDict(idx,loop) ) for idx,loop in enumerate(self.server.loops) ]
        
        request.send( '\n'.join( loopList ) )


    def process_updateloop( self, request, loop_key, interval ):
        """! @brief process 'lsloop' command
        """

        if loop_key in self.server.loops:
            self.server.loops[ loop_key ]['interval'] = float(interval)
            
            request.send('interval of loop "{k}" has been updated.'.format(k=loop_key))
        else:
            request.send('invalid key.')
        

    def process_lslogger( self, request ):
        """! @brief process 'lslogger' command
        """

        response = ["Logger setting"]
        response.append("--------------")
        for lCategory in sorted(self.server.logger.logCategories.keys()):
            setting = self.server.logger.logCategories[lCategory]
            response.append( "{s:>20} : {value}".format(s=lCategory, value=str(setting) ) )

        request.send( '\n'.join( response ) )

            
    def process_activatelogger( self, request, logger ):
        """ ! @brief process 'activatelogger' command
        """

        if logger in self.server.logger.logCategories:
            # turn on logger
            self.server.logger.logCategories[ logger ] = True
            
            request.send("logger '{l}' has been turned on.".format(l=logger) )
            
            return
                
        request.send("nothing has been done.")

    def process_deactivatelogger( self, request, logger ):
        """ ! @brief process 'deactivatelogger' command
        """

        if logger in self.server.logger.logCategories:
            # turn off logger
            self.server.logger.logCategories[ logger ] = False
            
            request.send("logger '{l}' has been turned off.".format(l=logger) )
            
            return
                
        request.send("nothing has been done.")


