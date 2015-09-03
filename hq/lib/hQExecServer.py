
from datetime import datetime
from time import sleep
import threading
from sqlalchemy import and_, not_, func
from operator import itemgetter, attrgetter
from sqlalchemy.orm.exc import NoResultFound
import tempfile
import subprocess
import pwd
import os
import json
import sys
import traceback
from pprint import pprint as pp
import getpass

# import hq libraries
from hq.lib.hQBaseServer import hQBaseServer,hQBaseServerHandler,hQBaseRequestProcessor
from hq.lib.hQServerDetails import hQServerDetails
from hq.lib.hQDBConnection import hQDBConnection
from hq.lib.hQCommand import hQCommand
from hq.lib.hQSocket import hQSocket
from hq.lib.daemon import Daemon
import hq.lib.hQDatabase as db


# get stored host and port from hq-user-server
hqServerDetails = hQServerDetails('hq-user-server')

HQU_SERVER_HOST = hqServerDetails.get('host', None)
HQU_SERVER_PORT = hqServerDetails.get('port', None)

USER = getpass.getuser()

class hQExecServer(hQBaseServer, Daemon):
    server_type ='hq-exec-server'
    
    def __init__(self, port):
        handler = hQExecServerHandler
        processor = hQExecServerRequestProcessor()

        self.user=USER

        super( hQExecServer, self ).__init__( port, handler, processor )

        # connect to database
        dbconnection = hQDBConnection()

        # get database id of host
        try:
            self.host_id = dbconnection.query( db.Host.id ).filter( db.Host.full_name==self.host ).one()[0]
        except:
            sys.stderr.write( "Host is not in cluster!" )
            sys.exit(-1)

        # set interval for loop of calling loop functions
        self.loops = { 'print_status': { 'fct': self.loop_print_status,
                                         'interval': 60,
                                         'description': "print periodically status of server" }
                       }

        # flags which indicate running processes
        self.printing_status = threading.Event()

        self.user_id = 1

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
        countsDict = {'hosts': slotInfo[0],
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
            
        

class hQExecServerHandler( hQBaseServerHandler ):
    def __init__( self, request, clientAddress, server ):
        super(hQExecServerHandler, self).__init__( request, clientAddress, server )


class hQExecServerRequestProcessor( hQBaseRequestProcessor ):
    def __init__( self ):
        super( hQExecServerRequestProcessor, self ).__init__()
        
        self.commands["RUN"] = hQCommand( name = "run",
                                          regExp = "^run:(.*)",
                                          arguments = ["job_id"],
                                          help = "message from hq-server to run job",
                                          fct = self.process_run )
        
        
    def process_run( self, request, job_id ):
        """ ! @brief process 'addjobs' command

        @param job_id Job.id of job which will be executed here

        """

        try:
            job_id = int( job_id )

            # connect to database
            dbconnection = hQDBConnection()

            # get job instance
            job = dbconnection.query( db.Job ).get( job_id )

            command = job.command
            shell = job.shell

            # create temporary file object for stdout and stderr of executing command
            fOut = tempfile.NamedTemporaryFile(prefix="hq-es.", bufsize=0, delete=True)
            fErr = tempfile.NamedTemporaryFile(prefix="hq-es.", bufsize=0, delete=True)

            startTime = datetime.now()

            self.writeLog('job ({j}) has been started at {t}'.format(j=job_id,t=str(startTime)),
                          logCategory="request_processing")

            ###############################
            # execute job in a subprocess #
            ###############################
            sp = subprocess.Popen( command,
                                   shell=True,
                                   cwd=os.path.expanduser("~"),
                                   executable=shell,
                                   stdout=fOut,
                                   stderr=fErr )

            ### tell server that job has been started
            ##clientSock = hSocket(host=self.host,
            ##                     port=self.port,
            ##                     EOCString=self.EOCString,
            ##                     sslConnection=self.sslConnection,
            ##                     certfile=certfile,
            ##                     keyfile=keyfile,
            ##                     ca_certs=ca_certs,
            ##                     catchErrors=False)
            ##
            ##clientSock.send("jobstarted:{jobID}".format(jobID=jobID))
            ##clientSock.close()

            # store info about running job in database

            # set job as running
            dbconnection.query( db.JobDetails.job_id ).\
              filter( db.JobDetails.job_id==job_id ).\
              update( {db.JobDetails.job_status_id: self.server.database_ids['running'] } )

            job.job_details.host_id = self.server.host_id
            job.job_details.pid = sp.pid

            # set history
            jobHistory = db.JobHistory( job=job,
                                        job_status_id = self.server.database_ids['running'] )

            dbconnection.introduce( jobHistory )
            dbconnection.commit()
            dbconnection.remove()

            ###################################
            # wait until process has finished #
            sp.wait()
            ###################################

            endTime = datetime.now()

            self.writeLog( 'job ({j}) has been finished at {t}'.format(j=job_id, t=str(endTime)),
                           logCategory="request_processing" )

            # connect to database
            dbconnection = hQDBConnection()

            # get job instance (again, since we use here another connection)
            job = dbconnection.query( db.Job ).get( job_id )

            ##################################################
            # write command, stdout, and stderr to a files   #

            if job.stdout:
                # copy temporary file for stdout
                try:
                    shutil.copyfile( fOut.name, job.stdout )
                except:
                    # error while opening or writing file
                    # what to do??
                    pass

            if job.stderr:
                # copy temporary file for stderr
                try:
                    shutil.copyfile( fErr.name, job.stderr )
                except:
                    # error while opening or writing file
                    # what to do??
                    pass

            if job.logfile:
                # write
                try:
                    # write logfile
                    p = os.path.expanduser( job.logfile )
                    with open(p, 'w') as f:

                        f.write("-----------------------\n")
                        f.write("--------command--------\n")
                        f.write("-----------------------\n")

                        f.write("%s\n" %command)
                        f.write("\n")

                        f.write("-----------------------\n")
                        f.write("----------info---------\n")
                        f.write("-----------------------\n")

                        f.write("host: {0}\n".format(os.uname()[1]))
                        f.write("started: %s\n" % (startTime))
                        f.write("finished: %s\n" % (endTime))
                        f.write("running time: %s\n" % (endTime-startTime) )
                        f.write("\n")

                        f.write("-----------------------\n")
                        f.write("------BEGIN stdout-----\n")
                        f.write("-----------------------\n")

                        fOut.seek(0)

                        for line in fOut:
                            f.write("%s" % line)

                        f.write("-----------------------\n")
                        f.write("------END stdout-------\n")
                        f.write("-----------------------\n")

                        f.write("\n")

                        f.write("-----------------------\n")
                        f.write("------BEGIN stderr-----\n")
                        f.write("-----------------------\n")

                        fErr.seek(0)
                        for line in fErr:
                            f.write("%s" % line)

                        f.write("-----------------------\n")
                        f.write("------END stderr-------\n")
                        f.write("-----------------------\n")

                except:
                    # error while opening or writing file
                    # what to do??
                    print traceback.print_exc()
                    pass

            fOut.close()
            fErr.close()

            # set job as finished
            dbconnection.query( db.JobDetails.job_id ).\
              filter( db.JobDetails.job_id==job_id ).\
              update( {db.JobDetails.job_status_id: self.server.database_ids['finished'] } )

            job.job_details.return_code = sp.returncode

            # set history
            jobHistory = db.JobHistory( job=job,
                                        job_status_id = self.server.database_ids['finished'] )

            dbconnection.introduce( jobHistory )

            finishedJob = db.FinishedJob( job=job )

            dbconnection.introduce( finishedJob )
            dbconnection.commit()
            dbconnection.remove()

        except:
            # something went wrong.
            print traceback.print_exc()
            pass

