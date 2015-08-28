
from datetime import datetime
from time import sleep
import threading
from sqlalchemy import and_, not_, func
from operator import itemgetter, attrgetter
from sqlalchemy.orm.exc import NoResultFound
import pwd
import os
import json
import sys
from copy import deepcopy
from collections import defaultdict
import traceback
from pprint import pprint as pp

# import hq libraries
from lib.hQBaseServer import hQBaseServer,hQBaseServerHandler,hQBaseRequestProcessor
from lib.hQServerDetails import hQServerDetails
from lib.hQDBConnection import hQDBConnection
from lib.hQCommand import hQCommand
from lib.hQSocket import hQSocket
from lib.hQServerProxy import hQServerProxy
from lib.daemon import Daemon
import lib.hQDatabase as db


# get stored host and port from the main server
hqServerDetails = hQServerDetails('hq-server')

HQ_SERVER_HOST = hqServerDetails.get('host', None)
HQ_SERVER_PORT = hqServerDetails.get('port', None)

USER = pwd.getpwuid(os.getuid())[0]

class hQUserServer(hQBaseServer, Daemon):
    server_type ='hq-user-server'
    
    def __init__(self, port):
        handler = hQUserServerHandler
        processor = hQUserServerRequestProcessor()

        self.user=USER

        super( hQUserServer, self ).__init__( port, handler, processor )

        # connect to hq-server and register hq-user-server
        try:
            allowed = self.register_server()
            if not allowed:
                sys.stderr.write( "Your are not alowed to use the hq pacakge.\nPlease contact your hq administrator." )
                sys.exit( -1 )
        except:
            sys.stderr.write( "hq server ist not running\nPlease contact your hq administrator." )
            sys.exit( -1 )
            
        # connect to database
        dbconnection = hQDBConnection()

        # set interval for loop of calling loop functions
        self.loops = { 'print_status': { 'fct': self.loop_print_status,
                                         'interval': 60,
                                         'description': "print periodically status of server" }
                       }

        self.exec_servers = {}

        # flags which indicate running processes
        self.printing_status = threading.Event()
        self.not_invoking_exec_server = {}
        
        # print status to stdout
        #self.print_status( short=True )


    def register_server( self ):
        """! @brief register server at hq-server

        if hq-server does not approve it, this server exits
        """
        jsonObj = json.dumps( { 'user': USER,
                                'host': self.host,
                                'port': self.port,
                                'id': self.server_id } )
        cmd = 'register:{j}'.format(j = jsonObj )
        clientSock = hQSocket( catchErrors = False )
        clientSock.initSocket( HQ_SERVER_HOST, HQ_SERVER_PORT )
        clientSock.send( cmd )
        
        response = clientSock.recv()
        response = json.loads( response )
        
        if response['status']=='approved':
            self.user_id = response['user_id']
            return True
        else:
            return False


    def get_status( self ):
        """! @brief get status of server from database """
        dbconnection = hQDBConnection()

        self.logger.write( "print status: request database about status",
                           logCategory='debug' )

        # get all number of jobs for each status type
        query = dbconnection.query( db.JobStatus.name,
                                    func.count('*') )\
                                    .join( db.JobDetails )\
                                    .join( db.Job )\
                                    .filter( db.Job.user_id==self.user_id )\
                                    .group_by( db.JobStatus.name )

        counts = dict( query.all() )

        if not counts:
            # no jobs so far in the database
            counts = {}

        self.logger.write( "print status: get slot info",
                           logCategory='debug' )
        slotInfo = dbconnection.query( func.count('*'),
                                       func.sum( db.Host.max_number_occupied_slots ), 
                                       func.sum( db.HostSummary.number_occupied_slots ) )\
                                       .select_from( db.Host )\
                                       .join( db.HostSummary, db.HostSummary.host_id==db.Host.id )\
                                       .filter( db.HostSummary.active==True )\
                                       .one()

        if slotInfo[0]==0:
            slotInfo = (0, 0, 0)

        dbconnection.remove()
        countsDict = { 'hosts': slotInfo[0],
                       'oSlots': slotInfo[2],
                       'tSlots': slotInfo[1],
                       'wJobs': counts.get('waiting',0),
                       'pJobs': counts.get('pending',0),
                       'rJobs': counts.get('running',0),
                       'fJobs': counts.get('finished',0)
                      }
        
        return countsDict


    def print_status(self, returnString=False, short=False):
        """!@brief print status of server to stdout if not outSream is given

        @param returnString (boolean) return formatted status instead of passing it to logger

        @return
        """
        if returnString or not self.printing_status.is_set():
            if not returnString:
                # set flag
                self.printing_status.set()

            t = datetime.now()
            
            statusDict = self.get_status()

            if short:
                status = "[occupied slots:{oSlots:>3}/{tSlots:>3}] [waiting jobs:{wJobs:>3}]".format(**statusDict)
            else:
                hl = "--------------------------------------------------"
                info = "[{t}] STATUS OF HQ-SERVER ON {h}:{p}".format(t=t, h=self.host, p=self.port)
                
                status = ""
                status += "{s:>20} : {value}\n".format(s="active hosts", value=statusDict['hosts'] )
                status += "{s:>20} : {value}\n".format(s="occupied slots", value="{occupied} / {total}".format(occupied=statusDict['oSlots'],total=statusDict['tSlots']) )
                status += "{s:>20} : {value}\n".format(s="waiting jobs", value=statusDict['wJobs'] )
                status += "{s:>20} : {value}\n".format(s="pending jobs", value=statusDict['pJobs'] )
                status += "{s:>20} : {value}\n".format(s="running jobs", value=statusDict['rJobs'] )
                status += "{s:>20} : {value}".format(s="finished jobs", value=statusDict['fJobs'] )
                
                status = "{info}\n{hl}\n{status}\n{hl}\n".format(hl=hl, info=info, status=status)
            
            if not returnString:
                self.logger.write( status,
                                   logCategory="status" )
                self.printing_status.clear()
            else:
                return status


    def loop_print_status( self, interval ):
        """! @brief"""
        while True:
            # wait a little bit
            sleep( interval )
            
            self.print_status(short=True)
        

    def loop_check_db( self ):
        """! @brief

        """
        pass

    def get_exec_server( self,
                         host_id,
                         host_name,
                         do_not_invoke=False,
                         logger=None,
                         delay=0 ):
        """! @brief invoke exec server on given host if necessary
        """

        if not logger:
            logger=self.logger.write
            
        if host_id not in self.not_invoking_exec_server:
            # create new event
            self.not_invoking_exec_server[ host_id ] = threading.Event()
        elif not self.not_invoking_exec_server[ host_id ].wait( 10 ):	# wait until event has been set. maximal 10s
            logger("TIMEOUT",logCategory="debug")

            # clear event
            self.not_invoking_exec_server[host_id].set()

            return None
        
        # unset event which indicates that a exec server is currently invoking
        self.not_invoking_exec_server[host_id].clear()

        
        if host_id not in self.exec_servers or not self.exec_servers[ host_id ]:
            # create a server proxy for hq-exec-server

            for cnt,delay in enumerate([0,2,5]):
                logger( "sleep for {t}s".format(t=delay) )
                sleep( delay )
            
                logger( "{c}. attempt to get exec server proxy for host {h}".format( c=cnt+1,
                                                                                     h=host_name ),
                        logCategory="debug" )
        
                ExecServer = hQServerProxy( host = host_name,
                                            serverType = "exec-server" )

                if do_not_invoke:
                    # just connect to server without invoking it
                    ExecServer.connect()
                else:
                    # connect 
                    ExecServer.run()

                if ExecServer.isRunning():
                    self.exec_servers[ host_id ] = ExecServer
                    logger( "get exec server proxy for host {h}:{p}".format( h=ExecServer.host,
                                                                             p=ExecServer.port ) )
                    break
                else:
                    self.exec_servers[ host_id ] = None
                    logger( "getting exec server proxy for host {h} failed".format( h=host_name ) )
            
        else:
            ExecServer = self.exec_servers[ host_id ]
            
            # check if server is responsive
            if not ExecServer.isRunning():
                self.exec_servers[ host_id ] = None
            
        # clear event
        self.not_invoking_exec_server[host_id].set()

        return self.exec_servers[ host_id ]


    def shutdown_server( self ):
        """! @brief extends hQBaseServer.shutdown_server() """
        
        for hostID in self.exec_servers:
            try:
                ExecServer = self.exec_servers[ hostID ]

                self.logger.write('Shutdown hq-exec-server on {host}:{port}'.format(host=ExecServer.host,
                                                                                    port=ExecServer.port),
                                  logCategory='system' )

                ExecServer.shutdown()
            except:
                print traceback.print_exc()
                pass
        
        super( hQUserServer, self ).shutdown_server()

        
class hQUserServerHandler( hQBaseServerHandler ):
    def __init__( self, request, clientAddress, server ):
        super(hQUserServerHandler, self).__init__( request, clientAddress, server )


class hQUserServerRequestProcessor( hQBaseRequestProcessor ):
    def __init__( self ):
        super( hQUserServerRequestProcessor, self ).__init__()
        
        self.commands["LSS"] = hQCommand( name = "lss",
                                          regExp = "^lss$",
                                          help = "return list of hq-exec-servers",
                                          fct = self.process_lss )
        self.commands["INVOKESERVERS"] = hQCommand( name = "invokeservers",
                                              regExp = "^invokeservers$",
                                              help = "invoke all hq-exec-servers of hosts in cluster",
                                              fct = self.process_invokeservers )
        self.commands["CLEANUP"] = hQCommand( name = "cleanup",
                                          regExp = "^cleanup$",
                                          help = "cleanup servers",
                                          fct = self.process_cleanup )
        self.commands["ADD"] = hQCommand( name = "addjob",
                                             regExp = "^addjob:(.*)",
                                             arguments = ["json_str"],
                                             help = "add multiple jobs at once to hq.",
                                             fct = self.process_addjob )
        self.commands["ADDJOBS"] = hQCommand( name = "addjobs",
                                              regExp = "^addjobs:(.*)",
                                              arguments = ["json_str"],
                                              help = "add multiple jobs at once to hq.",
                                              fct = self.process_addjobs )
        self.commands["RUN"] = hQCommand( name = "run",
                                          regExp = "^run:(.*)",
                                          arguments = ["json_str"],
                                          help = "message from hq-server to run jobs",
                                          fct = self.process_run )
        self.commands["LSWJOBS"] = hQCommand( name = 'lswjobs',
                                              regExp = '^lswjobs:?(.*)',
                                              arguments = ['num'],
                                              help = "return the last num waiting jobs. default: return the last 10. specify 'all' in order to return all waiting jobs",
                                              fct = self.process_lswjobs )
        self.commands["LSPJOBS"] = hQCommand( name = 'lspjobs',
                                              regExp = '^lspjobs:?(.*)',
                                              arguments = ['num'],
                                              help = "return the last num pending jobs. default: return the last 10. specify 'all' in order to return all pending jobs",
                                              fct = self.process_lspjobs )
        self.commands["LSRJOBS"] = hQCommand( name = 'lsrjobs',
                                              regExp = '^lsrjobs:?(.*)',
                                              arguments = ['num'],
                                              help = "return the last num running jobs. default: return the last 10. specify 'all' in order to return all running jobs",
                                              fct = self.process_lsrjobs )
        self.commands["LSFJOBS"] = hQCommand( name = 'lsfjobs',
                                              regExp = '^lsfjobs:?(.*)',
                                              arguments = ['num'],
                                              help = "return the last num finished jobs. default: return the last 10. specify 'all' in order to return all finished jobs",
                                              fct = self.process_lsfjobs )
        self.commands["LAJOB"] = hQCommand( name = 'lajob',
                                            regExp = 'lajob:(.*)',
                                            arguments = ["job_id"],
                                            help = "return job info about job with given jobID",
                                            fct = self.process_lajob )
        self.commands["FINDJOBS"] = hQCommand( name = 'findjobs',
                                               regExp = 'findjobs:(.*)',
                                               arguments = ["match_str"],
                                               help = "return all jobs which match the search string in command, info text or group.",
                                               fct = self.process_findjobs )
        
        
    def process_lss( self, request ):
        """ ! @brief process 'lss' command
        """
        
        # connect to database
        dbconnection = hQDBConnection()

        response = ""

        hosts = dict( dbconnection.query( db.Host.id, db.Host.full_name ).all() )
        for idx,hostID in enumerate( hosts ):
            host_fullname = hosts[ hostID ]
            ExecServer = self.server.get_exec_server( hostID, host_fullname, do_not_invoke=True )

            if ExecServer:
                response += "{idx} - [host:{host}] [port:{port}] [status:{status}]\n".format( idx=idx,
                                                                                              host=host_fullname,
                                                                                              port=ExecServer.port if ExecServer else '?',
                                                                                              status="running" if ExecServer else "not running" )

        if response:
            request.send( response )
        else:
            request.send("no servers known.")


    def process_invokeservers( self, request):
        # connect to database
        dbconnection = hQDBConnection()

        hosts = dbconnection.query( db.Host ).join( db.HostSummary ).filter( and_(db.HostSummary.available==True,
                                                                                  db.HostSummary.reachable==True,
                                                                                  db.HostSummary.active==True ) ).all()

        for host in hosts:
            hostID = host.id
            hostName = host.full_name

            ExecServer = self.server.get_exec_server( hostID, hostName )
            
            if not ExecServer:
                self.writeLog( "... could not start a hq-exec-server on {h}!\n".format(h=hostName),
                               logCategory='error')

        request.send("done")

        
    def process_cleanup( self, request ):
        """ ! @brief process 'cleanup' command
        """
        
        for hostID in self.server.exec_servers:
            try:
                ExecServer = self.server.exec_servers[ hostID ]

                self.writeLog('Shutdown hq-exec-server on {host}:{port}'.format(host=ExecServer.host,
                                                                                port=ExecServer.port),
                              logCategory='system' )

                ExecServer.shutdown()
            except:
                print traceback.print_exc()
                pass

        # forget all servers
        self.server.exec_servers = {}
        
        request.send( "done" )
            

    def process_addjob( self, request, json_str ):
        """ ! @brief process 'addjob' command

        @param json_str (json) json representation of a dictinary

        format of the dictinary
           { 'command': <string>,
             'estimatedMemory': <float>,
             'estimatedTime': <float>,
             'excludedHosts': <comma separated list of host names>,
             'group': <string>,
             'infoText': <string>,
             'logfile': <string>,
             'priority': <int>,
             'shell': <bash|csh>,
             'slots': <int>,
             'stderr': <string>,
             'stdout': <string> }

        """

        job = json.loads( json_str )
        
        # register job at TaskDispatcher
        jsonOutObj =  { 'user_id': self.server.user_id,
                        'host': self.server.host,
                        'port': self.server.port,
                        'id': self.server.server_id,
                        'jobs': [ job ] }

        #self.server.logger.info('[%s] ... submit jobs to cluster' % threadName)

        jsonOutObj = json.dumps(jsonOutObj)
        com = "add:%s" % jsonOutObj

        try:
            # instantiate new socket
            clientSock = hQSocket( catchErrors = False )
            clientSock.initSocket( HQ_SERVER_HOST, HQ_SERVER_PORT )
            clientSock.send( com )
            jobID = clientSock.recv()

            if jobID=="What do you want?":
                response = "Could not submit job to hq-server."
            else:
                response = "Job {ids} has been submitted to the cluster.\nSo long, and thanks for all the fish.".format(ids=jobID)
                
            request.send( response )
        except:
            traceback.print_exc(file=sys.stderr)
            request.send("Could not connect to hq-server.")


    def process_addjobs( self, request, json_str ):
        """ ! @brief process 'addjobs' command

        @parama json_str (json) json representation of a list of dictinaries

        format of each dictinary
           { 'command': <string>,
             'estimatedMemory': <float>,
             'estimatedTime': <float>,
             'excludedHosts': <comma separated list of host names>,
             'group': <string>,
             'infoText': <string>,
             'logfile': <string>,
             'priority': <int>,
             'shell': <bash|csh>,
             'slots': <int>,
             'stderr': <string>,
             'stdout': <string> }

        
        """
        
        jobs = json.loads( json_str )
        
        # register job at TaskDispatcher
        jsonOutObj =  { 'user_id': self.server.user_id,
                        'host': self.server.host,
                        'port': self.server.port,
                        'id': self.server.server_id,
                        'jobs': jobs }

        #self.server.logger.info('[%s] ... submit jobs to cluster' % threadName)

        jsonOutObj = json.dumps(jsonOutObj)
        com = "add:%s" % jsonOutObj

        try:
            # instantiate new socket
            clientSock = hQSocket( catchErrors = False )
            clientSock.initSocket( HQ_SERVER_HOST, HQ_SERVER_PORT )
            clientSock.send( com )
            jobID = clientSock.recv()

            if jobID=="What do you want?":
                response = "Could not submit job to hq-server."
            else:
                response = "Job {ids} has been submitted to the cluster.\nSo long, and thanks for all the fish.".format(ids=jobID)
                
            request.send( response )
        except:
            traceback.print_exc(file=sys.stderr)
            request.send("Could not connect to hq-server.")


    def process_run( self, request, json_str ):
        """ ! @brief process 'addjobs' command

        @param json_str (json) json representation of a dictinary

        dictinary has the following format:
          { <HOST.id>: { 'host_id': <int>},
                         'host_full_name': <string>,
                         'jobs': [<JOB.id>, ...], ... }
        """

        #jobs = json.loads( json_str )
        jobs = json.loads( json_str )

        failed = self._send_jobs( jobs )

        if failed:
            # there are still some jobs which could not be executed.
            # send them back
            failed_jobs = []
            [ failed_jobs.append( jobs[ h ]['jobs'] ) for h in failed ]

            cmd = "failedjobs:{j}".format(j=json.dumps( failed ) )

            clientSock = hQSocket( catchErrors = False )
            clientSock.initSocket( HQ_SERVER_HOST, HQ_SERVER_PORT )
            clientSock.send( cmd )

            
    def _send_jobs( self, jobs ):
        """! @brief send jobs to dedicated host by using a ExecServer proxy

        @param jobs (dict) jobs to sent grouped by host
        
        jobs dictinary has the following format:
          { <HOST.id>: { 'host_id': <int>},
                         'host_full_name': <string>,
                         'jobs': [<JOB.id>, ...], ... }
        """
        
        failed = []
        for host_id in jobs:
            host_name = jobs[ host_id ]['host_full_name']
            
            ExecServer = self.server.get_exec_server( host_id=host_id,
                                                      host_name=host_name,
                                                      logger=self.writeLog )

            if ExecServer:
                self.writeLog( "send jobs to exec server on {h}:{p}".format(h=ExecServer.host,
                                                                             p=ExecServer.port),
                               logCategory="debug" )
                for job_id in jobs[ host_id ]['jobs']:
                    response = ExecServer.sendAndClose( "run:{j}".format(j=job_id) )
            else:
                # could not establish a proxy for exec server on host host_name
                self.writeLog( "could not establish a proxy for {h}".format( h=host_name ),
                               logCategory="debug" )
                failed.append( host_id )
                
        return failed

       
    def _render_job_list( self, num, job_type ):
        """ ! @brief helper function for lswjobs, lspjobs, ...
        """

        if not num:
            # default
            num=10

        # connect to database
        dbconnection = hQDBConnection()

        query = dbconnection.query( db.Job )\
                .join( db.JobDetails )\
                .join( db.JobHistory )\
                .filter( db.JobDetails.job_status_id==self.server.database_ids[job_type] )\
                .filter( db.JobHistory.job_status_id==self.server.database_ids[job_type] )\
                .filter( db.Job.user_id==self.server.user_id )\
                .order_by( db.JobHistory.datetime.desc() )
        
        if num!='all':
            query = query.limit( int(num) )

        jobs = query.all()

        header = []
        response = []

        if job_type=="waiting":
            header.append( "Waiting jobs" )
            header.append( "------------" )
            
            jobString = "{i:3d} - [jobid:{id}] [user:{user}] [status:waiting since {t}] [group:{group}] [info:{info}] [command:{command}{dots}]"

        elif job_type=="pending":
            header.append( "Pending jobs" )
            header.append( "------------" )
            
            jobString = "{i:3d} - [jobid:{id}] [user:{user}] [status:pending on {host} since {t}] [group:{group}] [info:{info}] [command:{command}{dots}]\n"

        elif job_type=="running":
            header.append( "Running jobs" )
            header.append( "------------" )
            
            jobString = "{i:3d} - [jobid:{id}] [user:{user}] [status:running on {host} since {t}] [group:{group}] [info:{info}] [command:{command}{dots}]"

        elif job_type=="finished":
            header.append( "Finished jobs" )
            header.append( "------------" )
            
            jobString = "{i:3d} - [jobid:{id}] [user:{user}] [status:finished since {t}] [group:{group}] [info:{info}] [command:{command}{dots}]"
        
        
        for idx,job in enumerate(jobs):
            response.append( jobString.format( i=idx,
                                               id=job.id,
                                               user=job.user.name,
                                               t=str(job.job_history[-1].datetime),
                                               group=job.group,
                                               info=job.info_text,
                                               command=job.command[:30],
                                               dots="..." if len(job.command)>30 else "" ) )
        return "\n".join( header + response )
                

    def process_lswjobs( self, request, num ):
        """ ! @brief process 'lswjobs' command
        """
        
        rendered_response = self._render_job_list( num=num,
                                                   job_type='waiting' )
                             
        if rendered_response:
            request.send( rendered_response )
        else:
            request.send("no waiting jobs")


    def process_lspjobs( self, request, num ):
        """ ! @brief process 'lspjobs' command
        """
        
        rendered_response = self._render_job_list( num=num,
                                                   job_type='pending' )
                             
        if rendered_response:
            request.send( rendered_response )
        else:
            request.send("no pending jobs")


    def process_lsrjobs( self, request, num ):
        """ ! @brief process 'lsrjobs' command
        """
        
        rendered_response = self._render_job_list( num=num,
                                                   job_type='running' )
                             
        if rendered_response:
            request.send( rendered_response )
        else:
            request.send("no running jobs")


    def process_lsfjobs( self, request, num ):
        """ ! @brief process 'lsfjobs' command
        """

        rendered_response = self._render_job_list( num=num,
                                                   job_type='finished' )
                             
        if rendered_response:
            request.send( rendered_response )
        else:
            request.send("no finished jobs")

                
    def process_lajob( self, request, job_id ):
        """ ! @brief process 'lajob' command
        """
        
        # connect to database
        dbconnection = hQDBConnection()
            
        job = dbconnection.query( db.Job ).get( int(job_id) )

        if job:
            response = ""
            response += "{s:>20} : {value}\n".format(s="job id", value=job.id )
            response += "{s:>20} : {value}\n".format(s="command", value=job.command )
            response += "{s:>20} : {value}\n".format(s="info text", value=job.info_text )
            response += "{s:>20} : {value}\n".format(s="group", value=job.group )
            response += "{s:>20} : {value}\n".format(s="stdout", value=job.stdout )
            response += "{s:>20} : {value}\n".format(s="stderr", value=job.stderr )
            response += "{s:>20} : {value}\n".format(s="logfile", value=job.logfile )
            response += "{s:>20} : {value}\n".format(s="excludedHosts", value=job.excluded_hosts )
            response += "{s:>20} : {value}\n".format(s="slots", value=job.slots )

            for idx,hist in enumerate(job.job_history):
                if idx==0: s = "status"
                else: s=""

                response += "{s:>20} : [{t}] {status}\n".format(s=s, t=str(hist.datetime), status=hist.job_status.name )

            try:
                response += "{s:>20} : {value}\n".format(s="host", value=job.job_details.host.short_name )
            except:
                response += "{s:>20} : {value}\n".format(s="host", value="None" )
            response += "{s:>20} : {value}\n".format(s="pid", value=job.job_details.pid )
            response += "{s:>20} : {value}\n".format(s="return code", value=job.job_details.return_code )

            request.send( response )
        else:
            request.send("unkown job.")


    def process_findjobs( self, request, match_str ):
        """ ! @brief process 'findjobs' command
        """
        
        # connect to database
        dbconnection = hQDBConnection()

        jobs = dbconnection.query( db.Job ).filter( or_( db.Job.command.ilike( '%{s}%'.format(s=match_str) ),
                                                         db.Job.info_text.ilike( '%{s}%'.format(s=match_str) ),
                                                         db.Job.group.ilike( '%{s}%'.format(s=match_str) ) ) ).all()

        response = []
        response.append( "Matching jobs" )
        response.append( "-------------" )

        jobString = "{i:3d} - [jobid:{id}] [user:{user}] [status:{status}] [group:{group}] [info:{info}] [command:{command}{dots}]"
        for idx,job in enumerate(jobs):
            response.append( jobString.format( i=idx,
                                               id=job.id,
                                               user=job.user.name,
                                               status=job.job_details.job_status.name,
                                               group=job.group,
                                               info=job.info_text,
                                               command=job.command[:30],
                                               dots="..." if len(job.command)>30 else "" ) )
                             
        if jobs:
            request.send( '\n'.join( response ) )
        else:
            request.send("no jobs found")
            


