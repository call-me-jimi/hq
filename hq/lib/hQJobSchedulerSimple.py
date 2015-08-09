
from sqlalchemy import and_, not_, func
import json
from random import choice
import traceback
from operator import attrgetter
from collections import defaultdict

from hQDBConnection import hQDBConnection
import hQDatabase as db

class hQJobSchedulerSimple( object ):
    def __init__( self ):
        pass

    def next( self, numJobs=1, excludedJobIDs=set([]), returnInstances=False, logFct=None ):
        """! @brief get next jobs which will be send to cluster

        @param numJobs (int) maximal number of jobs which will be returned
        @param excludedJobIDs (set) set of jobIDs which should not be considered
        @param returnInstances (bool) if True return db.Job instances otherwise return job ids

        @return (list) job ids or db.Job
        
        @todo think about something more sophisticated than just taking the next in queue
        """

        dbconnection = hQDBConnection()

        # assign a dummyLog function to logFct if 
        if logFct:
            self.logFct = logFct
        else:
            def dummyLog( *args, **kargs ):
                return
            
            self.logFct = dummyLog
        
        # get list of tuples (<job.id>,<host.id>)
        nextJobs = []
        # get newly occupied slots grouped by host id
        newlyOccupiedSlots = defaultdict( int )

        # get next waiting job in queue
        self.logFct( "   get maximal {n} waiting jobs ...".format( n=numJobs ),
                     logCategory="job_scheduler" )
        
        if excludedJobIDs:
            jobs = dbconnection.query( db.WaitingJob ).\
                   join( db.User ).\
                   join( db.Job ).\
                   filter( db.User.enabled==True ).\
                   filter( not_(db.Job.id.in_(excludedJobIDs) ) ).\
                   order_by( db.WaitingJob.priorityValue ).\
                   limit( numJobs ).all()
            
        else:
            jobs = dbconnection.query( db.WaitingJob ).\
                   join( db.User ).\
                   filter( db.User.enabled==True ).\
                   order_by( db.WaitingJob.priorityValue.desc() ).\
                   limit( numJobs ).all()
            
        self.logFct( "   ... found {n} jobs".format(n=len(jobs)),
                     logCategory="job_scheduler" )


        # iterate over all jobs
        for idx,wJob in enumerate(jobs):
            # get owner of current job
            job = wJob.job
            user = job.user
            
            self.logFct( "     {idx}/{N} get vacant host for job {i} of user {u}".format( idx=idx+1,
                                                                                     N=len(jobs),
                                                                                     i=job.id,
                                                                                     u=user.name ),
                         logCategory="sendingjobs" )

            # get excluded hosts
            excludedHosts = json.loads( job.excluded_hosts )

            # get vacant host which has the required number of free slots. jobs which have been
            # processed here but have not been started are also considered
            vacantHost = self.get_vacant_host( job.slots,
                                               newlyOccupiedSlots,
                                               excludedHosts=set( excludedHosts ) )

            if vacantHost:
                if returnInstances:
                    nextJobs.append( (user, job, vacantHost) )
                else:
                    nextJobs.append( (user.id, job.id, vacantHost.id) )
                    
                newlyOccupiedSlots[ vacantHost.id ] += job.slots
                

        return nextJobs
    
        #if jobs:
        #    # return job id
        #    if returnInstances:
        #        return jobs
        #    else:
        #        return [ j.job_id for j in jobs ]
        #else:
        #    # no job was found
        #    return []

        
    def get_vacant_host( self, slots, slotDict, excludedHosts=set([]) ):
        """! @brief get vacant host which is not in excludedHosts and has at least slots unused slots

        @param slots (int) minimum number of free slots on vacant host
        @param slotDict (dict) newly occupied slots grouped by host
        @param excludedHosts (set) set of full names of host which should be excluded

        @return (@c Host|None)
        """

        #timeLogger = TimeLogger( prefix="getVacantHost" )
        
        dbconnection = hQDBConnection()
        
        self.logFct( "   find vacant host ...",
                     logCategory="job_scheduler" )
        
        if excludedHosts:
            hosts = dbconnection.query( db.Host )\
                    .join( db.HostSummary )\
                    .filter( and_(db.HostSummary.available==True,
                                  db.HostSummary.reachable==True,
                                  db.HostSummary.active==True,
                                  not_(db.Host.full_name.in_( excludedHosts ) ),
                                  db.Host.max_number_occupied_slots >= db.HostSummary.number_occupied_slots+slots
                                  ) )\
                    .all()
        else:
            hosts = dbconnection.query( db.Host ). \
              join( db.HostSummary ). \
              filter( and_(db.HostSummary.available==True,
                           db.HostSummary.reachable==True,
                           db.HostSummary.active==True,
                           db.Host.max_number_occupied_slots >= db.HostSummary.number_occupied_slots+slots ) ).all()

        if not hosts:
            self.logFct( "   ... no vacant host found.",
                         logCategory="sendingjobs" )
            
            return None
        else:
            # check load

            # pick randomly a host from list
            host = choice( hosts )
            hostSummary = host.host_summary
            
            # get latest load
            try:
                hostLoad = sorted( host.host_load, key=attrgetter( 'datetime' ) )[-1]
            except:
                # no load is given
                self.logFct( "   ... host {h} has no load in db. skip.".format(h=host.full_name),
                             logCategory="job_scheduler" )
                
                # get another vacant host
                excludedHosts.add( host.full_name )
                
                return self.get_vacant_host( slots, slotDict, excludedHosts=excludedHosts )

            expectedNewLoad = hostLoad.loadavg_1min + slotDict[ host.id ] + slots
            if expectedNewLoad <= 1.10 * host.total_number_slots:
                self.logFct( "   ... {h} is vacant. load is {l}. ok.".format(h=host.full_name,l=hostLoad.loadavg_1min),
                             logCategory="job_scheduler" )
                return host
            else:
                # load is too high
                self.logFct( "   ... {h} is vacant. load is {l}. too high. skip".format(h=host.full_name,l=hostLoad.loadavg_1min),
                             logCategory="job_scheduler" )

                # get another vacant host
                excludedHosts.add( host.full_name )
                
                return self.get_vacant_host( slots, slotDict, excludedHosts=excludedHosts )

            
    def setPriorities( self ):
        """! @brief set priorities of all waiting jobs

        1.0 + priority.value)/128
        """
        pass
    
