
from datetime import datetime,timedelta
from time import sleep
import threading
from sqlalchemy import and_, or_, not_, func
from operator import itemgetter, attrgetter
from sqlalchemy.orm.exc import NoResultFound
import json
import traceback
import sys
from collections import defaultdict
from pprint import pprint as pp

# import hq libraries
from hq.lib.hQBaseServer import hQBaseServer,hQBaseServerHandler,hQBaseRequestProcessor
from hq.lib.hQServerDetails import hQServerDetails
from hq.lib.hQDBConnection import hQDBConnection
from hq.lib.hQSocket import hQSocket
from hq.lib.hQCommand import hQCommand
from hq.lib.hQUtils import hQPingHost, hQHostLoad
from hq.lib.hQJobSchedulerSimple import hQJobSchedulerSimple
import hq.lib.hQDatabase as db

class hQServer(hQBaseServer):
    server_type ='hq-server'
    
    def __init__(self, port):
        processor = hQRequestProcessor()
        handler = hQServerHandler

        super( hQServer, self ).__init__( port, handler, processor )

        # set interval for loop of calling loop functions
        self.loops = { 'print_status': { 'fct': self.print_status,
                                         'kwargs': {'short': True},
                                         'interval': 5,
                                         'description': "print periodically status of server" },
                       'load_hosts': { 'fct': self.update_load_hosts,
                                       'interval': 5,
                                       'description': "update periodically load of hosts" },
                       'check_database': { 'fct': self.check_database,
                                           'interval': 1,
                                           'description': "check database for finished jobs and free occupied slots. afterwards, send jobs to user if there are free slots."}
                       }

        # events which indicate running processes
        self.sending_jobs = threading.Event()
        self.updating_load_hosts = threading.Event()

        self.jobScheduler = hQJobSchedulerSimple()
        
        # activity status of cluster
        self.active = threading.Event()

    
    def init_database_ids( self ):
        """! @brief save some database ids in self.database_ids
        """

        dbconnection = hQDBConnection()
        
        self.database_ids = dict( dbconnection.query( db.JobStatus.name, db.JobStatus.id ).all() )
        

        
    def get_status( self ):
        """! @brief get status of server from database """
        dbconnection = hQDBConnection()

        self.logger.write( "print status: request database about jobs status",
                           logCategory='debug' )

        # get all number of jobs for each status type
        query = dbconnection.query( db.JobStatus.name,
                                    func.count('*') )\
                .join( db.JobDetails )\
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

        statusDict = {'status': 'on' if self.active.is_set() else 'off',
                      'hosts': slotInfo[0],
                      'oSlots': slotInfo[2],
                      'tSlots': slotInfo[1],
                      'wJobs': counts.get('waiting',0),
                      'pJobs': counts.get('pending',0),
                      'rJobs': counts.get('running',0),
                      'fJobs': counts.get('finished',0)
                      }
        
        # connection has to be removed. otherwise calling hQDSession returns (in the same thread)
        # the same connection which doesn't see any updates in the meantime
        dbconnection.remove()
        
        return statusDict

        
    def print_status(self, returnString=False, short=False):
        """!@brief print status of server to stdout if not outSream is given

        @param returnString (boolean) return formatted status intsead of passing it to logger

        @return
        """
        
        statusDict = self.get_status()

        t = datetime.now()
        
        if short:
            status = "[status:{status}] [occupied slots:{oSlots:>3}/{tSlots:>3}] [waiting jobs:{wJobs:>3}]".format(**statusDict)
        else:
            hl = "--------------------------------------------------"
            info = "[{t}] STATUS OF HQ-SERVER ON {h}:{p}".format(t=t, h=self.host, p=self.port)
            status = ""
            status += "{s:>20} : {value}\n".format(s="cluster status", value=statusDict['status'] )
            status += "{s:>20} : {value}\n".format(s="active hosts", value=statusDict['hosts'] )
            status += "{s:>20} : {value}\n".format(s="occupied/total slots", value="{occupied} / {total}".format(occupied=statusDict['oSlots'],total=statusDict['tSlots']) )
            status += "{s:>20} : {value}\n".format(s="waiting jobs", value=statusDict['wJobs'] )
            status += "{s:>20} : {value}\n".format(s="pending jobs", value=statusDict['pJobs'] )
            status += "{s:>20} : {value}\n".format(s="running jobs", value=statusDict['rJobs'] )
            status += "{s:>20} : {value}".format(s="finished jobs", value=statusDict['fJobs'] )

            status = "{info}\n{hl}\n{status}\n{hl}\n".format(hl=hl, info=info, status=status)

        if returnString:
            # just return string
            return status
        else:
            # print status by logger
            self.logger.write( status,
                               logCategory="status" )

            
    def check_database( self ):
        """! @brief """

        self.logger.write( "check database",
                           logCategory='debug')

        # connection to database
        dbconnection = hQDBConnection()
        
        #timeLogger.log( "get finished jobs ..." )
        finishedJobs = dbconnection.query( db.FinishedJob ).all()
        #timeLogger.log( "... found {n}".format(n=len(finishedJobs) ) )

        if finishedJobs:
            self.logger.write( "{n} finished job{s}.".format(n=len(finishedJobs), s='s' if len(finishedJobs)>1 else '' ),
                               logCategory='debug' )

            occupiedSlots = defaultdict( int )

            for finishedJob in finishedJobs:
                job = finishedJob.job

                occupiedSlots[ job.job_details.host_id ] += job.slots

                dbconnection.delete( finishedJob )

            # free occupied slots on host
            for h in occupiedSlots:
                oSlots = occupiedSlots[h]
                self.logger.write( "free {n} slot{s} on host {h}".format( n=oSlots,
                                                                          s='s' if oSlots>1 else '', 
                                                                          h=h ),
                                     logCategory='debug' )

                dbconnection.query( db.HostSummary ).\
                                    filter( db.HostSummary.host_id==h ).\
                                    update( { db.HostSummary.number_occupied_slots: db.HostSummary.number_occupied_slots - oSlots } )

            dbconnection.commit()

        ## send jobs if possible

        if self.active.is_set():
            try:
                self.logger.write( "send waiting jobs ...",
                                   logCategory='debug')

                ## get next job, find vacant host and send job

                t1 = datetime.now()

                # get number of free slots
                #slotInfo = dbconnection.query( func.count('*'),
                #                               func.sum( db.Host.max_number_occupied_slots ), 
                #                               func.sum( db.HostSummary.number_occupied_slots ) ).select_from( db.Host ).join( db.HostSummary, db.HostSummary.host_id==db.Host.id ).filter( db.HostSummary.active==True ).one()
                #if slotInfo[1]!=None and slotInfo[2]!=None:
                #    freeSlots = slotInfo[1] - slotInfo[2]
                #else:
                #    freeSlots = 0

                hosts = dbconnection.query( db.Host.id,
                                            db.Host.total_number_slots,
                                            db.HostSummary.number_occupied_slots )\
                        .join( db.HostSummary )\
                        .all()

                totalNumSlots = sum( h[1] for h in hosts )
                numOccupiedSlots = sum( h[2] for h in hosts )

                freeSlots = totalNumSlots - numOccupiedSlots

                self.logger.write( "   free slots: {n}".format(n=freeSlots),
                                   logCategory="debug" )

                if freeSlots>0:
                    # get list [ (<jobID>,<hostID>), ... ]
                    jobs = self.jobScheduler.next( numJobs=freeSlots,
                                                   returnInstances=True,
                                                   logFct=self.logger.write  )
                    
                    jobsDict = defaultdict( list )

                    [ jobsDict[user.id].append( {'job': job,
                                                 'host': host } ) for (user,job,host) in jobs ]

                    for user_id in jobsDict:
                        user = dbconnection.query( db.User ).get( user_id )

                        if not self.ping_user( user, dbconnection ):
                            # hq user host is not reachable
                            # skip this user
                            break
                        
                        # group jobs by host
                        jobsGroupedByHost = {}
                        
                        for d in jobsDict[ user_id ]:
                            job = d['job']
                            host = d['host']

                            if host.id not in jobsGroupedByHost:
                                jobsGroupedByHost[ host.id ] = { 'host_id': host.id,
                                                                 'host_full_name': host.full_name,
                                                                 'jobs': []
                                                                 }
                            # set job as pending
                            dbconnection.query( db.JobDetails.job_id ).\
                              filter( db.JobDetails.job_id==job.id ).\
                              update( { db.JobDetails.job_status_id: self.database_ids['pending'],
                                        db.JobDetails.host_id: host.id } )

                            # reduce slots in host
                            dbconnection.query( db.HostSummary ).\
                              filter( db.HostSummary.host_id==host.id ).\
                              update( { db.HostSummary.number_occupied_slots: db.HostSummary.number_occupied_slots+job.slots })

                            # set history
                            jobHistory = db.JobHistory( job=job,
                                                        job_status_id = self.database_ids['pending'] )

                            # remove job from waiting list
                            dbconnection.query( db.WaitingJob ).filter( db.WaitingJob.job_id==job.id ).delete()

                            dbconnection.introduce( jobHistory )
                            
                            jobsGroupedByHost[ host.id ][ 'jobs' ].append( job.id )
                            
                            freeSlots -= job.slots
                                            
                        dbconnection.commit()

                        cmd = 'run:{l}'.format( l=json.dumps( jobsGroupedByHost ) )

                        self.send_to_user( cmd, user, dbconnection )
                        
                t2 = datetime.now()
                self.logger.write( "... done in {dt}s.".format(dt=str(t2-t1) ),
                                   logCategory="debug" )
            except:
                # error handling
                #traceback.print_exc(file=sys.stdout)
                print "error"

        # connection has to be removed. otherwise calling hQDSession returns (in the same thread)
        # the same connection which doesn't see any updates in the meantime
        dbconnection.remove()

    
    def set_reachability_hosts( self, hosts=[] ):
        """! @brief set reachability of hosts given in list or check all in database 
        
        @param hosts (list) list host full names

        @return (dict) dictinary with hosts and their reachability status
        """

        dbconnection = hQDBConnection()

        if not hosts:
            # get all hosts given in database
            hosts = map(itemgetter(0), dbconnection.query( db.Host.full_name ).all())
        
        self.logger.write( "Checking reachabilty of {n} host{s} ...".format( n=len(hosts), s="s" * int( len(hosts)>1 ) ),
                         logCategory='debug' )

        pingList = []
        for host in hosts:
            current = hQPingHost( host )
            pingList.append( current )
            current.start()

        reachability = {}
        for p in pingList:
             p.join()
             if p.status[1]>0:	# p.status: (transmitted,received)
                 # successful ping
                 self.logger.write( "     {h} ... is reachable".format( h=p.host ),
                                  logCategory='debug')

                 # set host in database as reachable
                 hostSummaryInstance = dbconnection.query( db.HostSummary )\
                                       .join( db.Host )\
                                       .filter( db.Host.full_name==p.host )\
                                       .one()
                 
                 hostSummaryInstance.reachable = True

                 reachability[ p.host ] = True
             else:
                 # unreachable
                 self.logger.write( "     {h} ... is not reachable".format( h=p.host ),
                                  logCategory='debug' )

                 # set host in database as not reachable
                 hostSummaryInstance = dbconnection.query( db.HostSummary )\
                                       .join( db.Host )\
                                       .filter( db.Host.full_name==p.host )\
                                       .one()
                 
                 hostSummaryInstance.reachable = False
                 hostSummaryInstance.active = False
                 
                 reachability[ p.host ] = False
                 
        dbconnection.commit()
        
        # connection has to be removed. otherwise calling hQDSession returns (in the same thread)
        # the same connection which doesn't see any updates in the meantime
        dbconnection.remove()
        
        return reachability

        

    def activate_host( self, host ):
        """! @brief set status of host to active if it is available and reachable

        @param host (string) full host name
        """

        dbconnection = hQDBConnection()
        
        reachability = self.set_reachability_hosts( hosts=[host] )
        
        if reachability[ host ]:
            try:
                hostSummaryInstance = dbconnection.query( db.HostSummary )\
                                      .join( db.Host )\
                                      .filter( db.Host.full_name==host )\
                                      .one()
                hostSummaryInstance.active = True

                dbconnection.commit()
                
                return 'activated'
            except:
                pass

        return

        
    def deactivate_host( self, host ):
        """! @brief set status of host to non-active

        @param host (string) full host name
        """

        dbconnection = hQDBConnection()

        try:
            hostSummaryInstance = dbconnection.query( db.HostSummary )\
                                  .join( db.Host )\
                                  .filter( db.Host.full_name==host )\
                                  .one()
            hostSummaryInstance.active = False

            dbconnection.commit()

            return 'deactivated'
        except:
            pass

        return 
        
            
    def update_load_hosts( self, hosts=[], force=False ):
        """! @brief set load of hosts (or of all given in database) by connecting to server and grep /proc/loadavg
        
        @param hosts (list) list Host instances
        @param force (bool) force update regardless of flag self.updating_load_hosts
        
        @return nothing
        """
        
        if force or not self.updating_load_hosts.is_set():
            if not force:
                # set flag
                self.updating_load_hosts.set()

            try:
                dbconnection = hQDBConnection()

                if not hosts:
                    # get all hosts given in database
                    hosts = dbconnection.query( db.Host ).\
                            join( db.HostSummary ). \
                            filter( and_(db.HostSummary.available==True,
                                         db.HostSummary.reachable==True ) ).all()

                hostsDict = { h.full_name: h for h in hosts }

                self.logger.write( "Checking load of {n} host{s} ...".format( n=len(hosts), s="s" * int( len(hostsDict)>1 ) ),
                                   logCategory='debug' )

                hostLoadList = []
                # iterate over keys
                for host in hostsDict:
                    current = hQHostLoad( host )
                    hostLoadList.append( current )
                    current.start()

                for p in hostLoadList:
                     p.join()
                     self.logger.write( "     {h} has load {l}".format( h=p.host, l=p.load[0] ),
                                        logCategory='debug' )

                     # update load in database
                     host = hostsDict[ p.host ]

                     # get all HostLoad instances attached to Host
                     hostLoads = dbconnection.query( db.HostLoad )\
                                 .join( db.Host )\
                                 .filter( db.Host.id==host.id )\
                                 .order_by( db.HostLoad.datetime )\
                                 .all()

                     # check whether there is a no newer entry
                     if len(hostLoads)==0 or hostLoads[-1].datetime<datetime.now():
                         # store only the last 5 load information
                         if len(hostLoads)>4:
                             # delete oldest one
                             dbconnection.delete( hostLoads[0] )

                         # create new HostLoad instance
                         hostLoad = db.HostLoad( host = host,
                                                 loadavg_1min = p.load[0],
                                                 loadavg_5min = p.load[1],
                                                 loadavg_10min = p.load[2] )

                         dbconnection.introduce( hostLoad )

                dbconnection.commit()

                # connection has to be removed. otherwise calling hQDSession returns (in the same thread)
                # the same connection which doesn't see any updates in the meantime
                dbconnection.remove()
            except:
                pass
            finally:
                if not force:
                    # set flag
                    self.updating_load_hosts.clear()
        
    def after_request_processing( self ):
        """! @brief is executed after a request came in
        """
        pass


    def ping_user( self, user, con ):
        """! @brief send ping to user server """
        now = datetime.now()

        try:
            if user.last_check + timedelta( seconds=user.idle_time ) < now:
                # ping user server
                sock = hQSocket( host=user.hq_user_server_host,
                                 port=user.hq_user_server_port,
                                 catchErrors=False)

                sock.send( "ping" )
                response = sock.recv()

                if response == 'pong':
                    user.idle_time = 0
                    user.last_check = now

                    con.commit()
                    
                    return True
                else:
                    self.logger.write( "hq-user-server of user {u} is not accesible.".format(u=user.name),
                                       logCategory="error")
                    user.idle_time = 1 if not user.idle_time else user.idle_time*2
                    user.last_check = now
                    
                    con.commit()
                    
                    self.logger.write( "{i}s until next check.".format(i=user.idle_time),
                                       logCategory="error")
                    
                    return False
            else:
                # user is still temporarily disabled
                # do nothing here
                pass
        except:
            #print traceback.print_exc()
            self.logger.write( "hq-user-server of user {u} is not accesible.".format(u=user.name),
                               logCategory="error")
            
            user.idle_time = 1 if not user.idle_time else user.idle_time*2
            user.last_check = now

            con.commit()
            
            self.logger.write( "{i}s until next check.".format(i=user.idle_time),
                               logCategory="error")
                    
            return False

        
    def send_to_user( self, cmd, user, con ):
        """! @brief send command to user """
        try:
            sock = hQSocket( host=user.hq_user_server_host,
                             port=user.hq_user_server_port,
                             catchErrors=False)

            sock.send( cmd )
        except:
            user.idle_time = 1 if not user.idle_time else user.idle_time*2
            user.last_check = now
                                              
            con.commit()
            
            self.logger.write( "error while sending somthing to hq-user-server of user {u}.".format(u=user.name),
                               logCategory="error")

        
class hQServerHandler( hQBaseServerHandler ):
    def __init__( self, request, clientAddress, server ):
        super(hQServerHandler, self).__init__( request, clientAddress, server )


    def finish( self ):
        """! @brief Send jobs to vacant hosts and cleanup handler afterwards

        Check database if there are waiting jobs, check user, find vacant host, and send job to associated tms of user.
        """
    
        super(hQServerHandler, self).finish()



class hQRequestProcessor( hQBaseRequestProcessor ):
    def __init__( self ):
        super( hQRequestProcessor, self ).__init__()
        
        self.commands["UPDATESLOTS"] = hQCommand( name = "updateslots",
                                                  regExp = "^updateslots$",
                                                  help = "update slot statistics",
                                                  fct=self.process_updateslots)
        self.commands["ACTIVATE"] = hQCommand( name = "activate",
                                              regExp = "^activate$",
                                              help = "activate cluster",
                                              fct = self.process_activate )
        self.commands["DEACTIVATE"] = hQCommand( name = "deactivate",
                                              regExp = "^deactivate$",
                                              help = "deactivate cluster",
                                              fct = self.process_deactivate )
        self.commands["LSCLUSTER"] = hQCommand( name = "lscluster",
                                              regExp = "^lscluster$",
                                              help = "return cluster details",
                                              fct = self.process_lscluster )
        self.commands["ACTIVATEHOST"] = hQCommand( name = "activatehost",
                                                   regExp = "^activatehost:(.*)",
                                                   arguments = ["host"],
                                                   help = "activate host, i.e., set status to active.",
                                                   fct = self.process_activatehost )
        self.commands["DEACTIVATEHOST"] = hQCommand( name = "deactivatehost",
                                                     regExp = "^deactivatehost:(.*)",
                                                     arguments = ["host"],
                                                     help = "deactivate host, i.e., set status to non-active.",
                                                     fct = self.process_deactivatehost )
        self.commands["UPDATELOAD"] = hQCommand( name = "updateload",
                                                 regExp = "^updateload$",
                                                 help = "update load of hosts",
                                                 fct = self.process_updateload )
        self.commands["REGISTER"] = hQCommand( name = "register",
                                               regExp = "^register:(.*)",
                                               arguments = ["json_obj"],
                                               help = "register user and updated his/hers server details.",
                                               fct = self.process_register )
        self.commands["ENABLEUSER"] = hQCommand( name = "enableuser",
                                                 arguments = ["user_name"],
                                                 regExp = "^enableuser:(.*)",
                                                 help = "enable user.",
                                                 fct = self.process_enableuser )
        self.commands["DISABLEUSER"] = hQCommand( name = "disableuser",
                                                  arguments = ["user_name"],
                                                  regExp = "^enableuser:(.*)",
                                                  help = "enable user.",
                                                  fct = self.process_disableuser)
        self.commands["LSUSERS"] = hQCommand( name = "lsusers",
                                              regExp = "^lsusers$",
                                              help = "return list of users",
                                              fct = self.process_lsusers )
        self.commands["LSUSER"] = hQCommand( name = "lsuser",
                                             regExp = "^lsuser:(.*)$",
                                             arguments = ["user_name"],
                                             help = "show all details about user.",
                                             fct = self.process_lsuser )
        self.commands["ADD"] = hQCommand( name = "add",
                                          regExp = "^add:(.*)",
                                          arguments = ["json_str"],
                                          help = "add (multiple) jobs to hq.",
                                          fct = self.process_addjobs )
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
        self.commands["RESETPJOBS"] = hQCommand( name = "resetpjobs",
                                                 regExp = "^resetpjobs$",
                                                 help = "set all pending jobs as finished. free occupied slots on hosts.",
                                                 fct = self.process_resetpjobs )
        self.commands["FAILEDJOBS"] = hQCommand( name = "failedjobs",
                                                 regExp = "^failedjobs:(.*)",
                                                 arguments = ["json_str"],
                                                 help = "info about jobs which could not be started",
                                                 fct = self.process_failedjobs )
        
    def process_updateslots( self, request ):
        """! @brief process 'activate' command
        """

        dbconnection = hQDBConnection()
        
        counts = dict( dbconnection.query( db.Host.id, func.sum( db.Job.slots ) ).\
                       join( db.JobDetails, db.JobDetails.host_id==db.Host.id ).\
                       join( db.JobStatus, db.JobDetails.job_status_id==db.JobStatus.id ).\
                       join( db.Job, db.JobDetails.job_id==db.Job.id ).\
                       filter( db.JobStatus.id.in_( [ self.server.database_ids['pending'],
                                                      self.server.database_ids['running'] ] ) ).\
                       group_by( db.Host.full_name ).all() )

        for h in dbconnection.query( db.HostSummary ):
            h.number_occupied_slots = counts.get( h.id, 0)

        dbconnection.commit()

        request.send( "number of occupied slots have been updated." )
            

    def process_activate( self, request ):
        """! @brief process 'activate' command
        """

        self.server.active.set()

        request.send('cluster has been activated')

        
    def process_deactivate( self, request ):
        """! @brief process 'deactivate' command
        """

        self.server.active.clear()

        request.send('cluster has been deactivated')
        
    def process_register( self, request, json_obj ):
        """! @brief process 'register' command
        """

        userDetails = json.loads( json_obj )
        
        con = hQDBConnection()

        try:
            user = con.query( db.User ).filter( db.User.name==userDetails['user'] ).one()
        except:
            print traceback.print_exc()
            request.send( json.dumps( {'status': 'disapproved' } ) )
            return
        
        # update user' server details
        user.hq_user_server_host = userDetails[ 'host' ]
        user.hq_user_server_port = userDetails[ 'port' ]
        user.hq_user_server_id = userDetails[ 'id' ]

        user.last_check = datetime.now()
        user.idle_time = 0
        
        con.commit()
        
        self.writeLog( 'user {u} has been registered.'.format(u=user.name),
                       logCategory='system' )

        request.send( json.dumps( {'status': 'approved', 'user_id': user.id} ) )
        
    def process_enableuser( self, request, user_name ):
        """! @brief process 'enableuser' command
        """

        con = hQDBConnection()

        try:
            con.query( db.User ).filter( db.User.name==user_name ).update( {db.User.enabled: True} )
            con.commit()

            request.send('done.')
        except:
            request.send('failed.')

    def process_disableuser( self, request, user_name ):
        """! @brief process 'disableuser' command
        """

        con = hQDBConnection()

        try:
            con.query( db.User ).filter( db.User.name==user_name ).update( {db.User.enabled: False} )
            con.commit()

            request.send('done.')
        except:
            request.send('failed.')

    def process_lsusers( self, request ):
        """ ! @brief process 'lsusers' command
        """

        dbconnection = hQDBConnection()
        
        users = dbconnection.query( db.User ).all()

        header = []
        header.append( "Users" )
        header.append("------")

        def _userDict( u ):
            return { 'name': u.name,
                     'status': 'enabled' if u.name else 'disabled',
                     'host': u.hq_user_server_host,
                     'port': u.hq_user_server_port,
                     'idle_time': u.idle_time }
        
        userStr = "{idx:3d}. {name} ({status}) {host}:{port} idle time: {idle_time}"
        
        userList = [ userStr.format( idx=idx, **_userDict( user ) ) for idx,user in enumerate(users) ]
        
        request.send( '\n'.join( header  + userList ) )
            
    def process_lsuser( self, request, user_name ):
        """ ! @brief process 'lauser' command
        """

        dbconnection = hQDBConnection()
        
        try:
            user = dbconnection.query( db.User )\
                   .filter( db.User.name==user_name )\
                   .one()

            response = []
            response.append( "Details about user {u}".format( u=user_name ) )
            response.append( "-----------------------------" )
            
            response.append( "{s:>20} : {value}".format(s="name", value=user.name ) )
            response.append( "{s:>20} : {value}".format(s="enabled", value='True' if user.enabled else 'False' ) )
            response.append( "{s:>20} : {value}".format(s="hq-user-server-host", value=user.hq_user_server_host ) )
            response.append( "{s:>20} : {value}".format(s="hq-user-server-port", value=user.hq_user_server_port ) )
            response.append( "{s:>20} : {value}".format(s="hq-user-server-id", value=user.hq_user_server_id ) )
            response.append( "{s:>20} : {value}".format(s="last_check", value=user.last_check ) )
            response.append( "{s:>20} : {value}".format(s="idle_time", value=user.idle_time ) )
            # numbe of jobs?
            
            request.send( '\n'.join( response ) )
        except:
            # maybe user name is not unique
            request.send('failed.')
            
        
    def process_lscluster( self, request ):
        """! @brief process 'lscluster' command
        """

        dbconnection = hQDBConnection()
        
        # show cluster
        hosts = dbconnection.query( db.Host ).all()

        response = "cluster is {s}\n".format( s='on' if self.server.active.is_set() else 'off' )
        response += "------------------------\n"

        for idx,host in enumerate(hosts):
            try:
                load = host.host_load[-1].loadavg_1min
            except:
                load = 'n.a.'

            hostInfo = { 'i': idx,
                         'name': host.full_name,
                         'status': 'active' if host.host_summary.active else 'reachable' if host.host_summary.reachable else 'available' if host.host_summary.available else 'not available',
                         'occupiedSlots': host.host_summary.number_occupied_slots,
                         'freeSlots': host.max_number_occupied_slots - host.host_summary.number_occupied_slots,
                         'maxSlots': host.max_number_occupied_slots,
                         'load': load
                         }
            response += "{i} - [host:{name}] [status:{status}] [free slots:{freeSlots}/{maxSlots}] [load:{load}]\n".format( **hostInfo )

        if response:
            request.send( response )
        else:
            request.send( "no hosts in cluster." )

    def process_activatehost( self, request, host ):
        """! @brief process 'activatehost' command

        @param host
        """

        status = self.server.activate_host( host )

        if status=='activated':
            request.send( "host {h} has been activated".format(h=host) )
        else:
            request.send( "nothing has been done" )

        #TD.activateHost( host )
        #
        #request.send( "host {h} has been activated".format(h=host) )
        #
        #
        #reachability = self.setReachabilityOfHosts( hosts=[host] )
        #
        #if reachability[ host ]:
        #    # maybe it is more efficient to use query().join().update( ) but in SQLite it is currently not supported (OperationalError)
        #    hostSummaryInstance = dbconnection.query( db.HostSummary ).join( db.Host ).filter( db.Host.full_name==host ).one()
        #    hostSummaryInstance.active = True
        #    
        #    dbconnection.commit()
        #
        #return 

    def process_deactivatehost( self, request, host ):
        """! @brief process 'activatehost' command

        @param host
        """

        status = self.server.deactivate_host( host )

        if status=='deactivated':
            request.send( "host {h} has been deactivated".format(h=host) )
        else:
            request.send( "nothing has been done" )

    def process_updateload( self, request ):
        """! @brief process 'updateload' command
        """
        
        # update load of hosts
        self.server.update_load_hosts()

        request.send( 'done.' )

        
    def process_addjobs( self, request, json_str ):
        """ ! @brief process 'addjobs' command
        """
        
        jsonObj = json.loads( json_str )

        dbconnection = hQDBConnection()
        
        user_id = jsonObj['user_id']
        hqUserServerHost = jsonObj['host']
        hqUserServerPort = jsonObj['port']
        hqUserServerID = jsonObj['id']
        
        # get user from database
        # !!! think about a better and more secure way to integrate users
        try:
            userInstance = dbconnection.query( db.User ).get( user_id )

            # update tms info at user
            userInstance.hq_user_server_host=hqUserServerHost
            userInstance.hq_user_server_port=hqUserServerPort
            userInstance.hq_user_server_id=hqUserServerID

            dbconnection.commit()
        except:
            self.writeLog( 'Unknown user {u}'.format(u=user_id),
                           logCategory='error' )
            traceback.print_exc(file=sys.stderr)
            request.send('Unknown user.')

        numJobs = len( jsonObj['jobs'] ) 
        jobIDs = []
        
        self.writeLog( "Add {n} job{s} ...".format(n=numJobs,
                                                   s='s' if numJobs>1 else '' ),
                     logCategory='system' )

        # iterate over all jobs
        for idx,job in enumerate(jsonObj['jobs']):
            command = job['command']
            slots = int(job['slots'])
            infoText = job.get('infoText','')
            group = job.get('group','')
            stdout = job.get('stdout','')
            stderr = job.get('stdin','')
            logfile = job.get('logfile','')
            shell = job['shell']
            excludedHosts = job.get("excludedHosts","").split(',')
            priorityValue = job.get('priority',0)
            estimatedTime = int(job.get("estimatedTime",0))
            estimatedMemory = int(job.get("estimatedmEMORY",0))

            # check excluded hosts
            excludedHostsList = []
            for h in excludedHosts:
                try:
                    dbconnection.query( db.Host ).filter( db.Host.full_name==h ).one()
                    excludedHostsList.append( h )
                except NoResultFound:
                    # do not consider this host
                    continue

            # priority value is supposed to be between  0 and 127
            priorityValue = 127 if priorityValue > 127 else 0 if priorityValue<0 else priorityValue
            # get database id of priority
            try:
                priority = dbconnection.query( db.Priority ).filter( db.Priority.value==priorityValue ).one()
            except NoResultFound:
                priority = db.Priority( value=priorityValue )
                dbconnection.introduce( priority )

            # create database entry for the new job
            newJob = db.Job( user_id=user_id,
                             command=command,
                             slots=int(slots),
                             priority=priority,
                             info_text=infoText,
                             group=group,
                             shell=shell,
                             stdout=stdout,
                             stderr=stderr,
                             logfile=logfile,
                             excluded_hosts=json.dumps( excludedHostsList ) )

            # set jobstatus for this job
            jobDetails = db.JobDetails( job=newJob,
                                        job_status_id=self.server.database_ids['waiting'] )

            # add as waiting job
            waitingJob = db.WaitingJob( job=newJob,
                                        user_id=user_id,
                                        priorityValue=priority.value )	# calculate a priority value

            # set history
            jobHistory = db.JobHistory( job=newJob,
                                        job_status_id = self.server.database_ids['waiting'] )

            dbconnection.introduce( newJob, jobDetails, waitingJob, jobHistory )

            dbconnection.commit()

            #self.writeLog( '  {idx}/{n}: added job with id {i}'.format( idx=idx+1,
            #                                                            n=numJobs,
            #                                                            i=newJob.id ),
            #             logCategory='request_processing')

            jobIDs.append( str(newJob.id) )

        request.send( json.dumps( jobIDs ) )


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
            


    def process_resetpjobs( self, request ):
        """ ! @brief process 'resetpjobs' command
        """
        
        dbconnection = hQDBConnection()
        
        # get all pending jobs
        pJobs = dbconnection.query( db.Job )\
                .join( db.JobDetails )\
                .filter( db.JobDetails.job_status_id==self.server.database_ids['pending'] )\
                .all()

        # get occupied slots of each host
        slots = dict( dbconnection.query( db.HostSummary.host_id, db.HostSummary.number_occupied_slots ).all() )

        occupiedSlots = defaultdict( int )
        for job in pJobs:
            occupiedSlots[ job.job_details.host_id ] += job.slots

            # set job as waiting
            dbconnection.query( db.JobDetails.job_id ).\
              filter( db.JobDetails.job_id==job.id ).\
              update( {db.JobDetails.job_status_id: self.server.database_ids['waiting'] } )

            # add to waiting jobs
            wJob = db.WaitingJob( job=job,
                                  user_id=job.user_id,
                                  priorityValue=job.priority.value )

            # set history
            jobHistory = db.JobHistory( job=job,
                                        job_status_id = self.server.database_ids['waiting'] )

            dbconnection.introduce( jobHistory, wJob )

        dbconnection.commit()

        # free occupied slots from host
        for h in occupiedSlots:
            dbconnection.query( db.HostSummary ).\
              filter( db.HostSummary.host_id==h ).\
              update( { db.HostSummary.number_occupied_slots: db.HostSummary.number_occupied_slots - occupiedSlots[ h ] } )

        dbconnection.commit()

        request.send( "set {n} jobs as waiting".format(n=len(pJobs)) )

    def process_failedjobs( self, request, json_str ):
        """ ! @brief process 'failedjobs' command
        
        @param json_str (json) json representation of a list with job_ids

        """

        job_ids = json.loads( json_str )
        
        dbconnection = hQDBConnection()

        # get job instances
        jobs = dbconnection.query( db.Job )\
               .filter( db.Job.id.in_( job_ids) )\
               .all()

        # get occupied slots of each host
        slots = dict( dbconnection.query( db.HostSummary.host_id,
                                          db.HostSummary.number_occupied_slots ).all() )

        occupiedSlots = defaultdict( int )
        for job in jobs:
            occupiedSlots[ job.job_details.host_id ] += job.slots

            # set job as waiting
            dbconnection.query( db.JobDetails.job_id ).\
              filter( db.JobDetails.job_id==job.id ).\
              update( {db.JobDetails.job_status_id: self.server.database_ids['waiting'] } )

            # add to waiting jobs
            wJob = db.WaitingJob( job=job,
                                  user_id=job.user_id,
                                  priorityValue=job.priority.value )

            # set history
            jobHistory = db.JobHistory( job=job,
                                        job_status_id = self.server.database_ids['waiting'] )

            dbconnection.introduce( jobHistory, wJob )

        dbconnection.commit()

        # free occupied slots from host
        for h in occupiedSlots:
            dbconnection.query( db.HostSummary ).\
              filter( db.HostSummary.host_id==h ).\
              update( { db.HostSummary.number_occupied_slots: db.HostSummary.number_occupied_slots - occupiedSlots[ h ] } )

        dbconnection.commit()

        request.send( "set {n} jobs as waiting".format(n=len(jobs)) )

