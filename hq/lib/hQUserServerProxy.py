
import os
import json
from copy import copy
from pprint import pprint as pp

# import hq libraries
from hq.lib.hQServerProxy import hQServerProxy

    
class hQUserServerProxy( hQServerProxy ):
    def __init__( self,
                  host = None,
                  logFile = "",
                  verboseMode = False,
                  persistent = False ):
        """! @brief Class for establishing a running User Server"""

        super( hQUserServerProxy, self ).__init__( serverType = 'hq-user-server',
                                                   host = host,
                                                   logFile = logFile,
                                                   verboseMode = verboseMode,
                                                   persistent = persistent )

        self.run()
        
    def add_jobs( self, job_list ):
        """! @brief add job to server

        @param job_list (list) list of jobs represented as dictinary

        """

        default_job_dict = { "slots": 1,
                             "group": "",
                             "infoText": "",
                             "logfile": "",
                             "stdout": "",
                             "stderr": "",
                             "shell": os.environ['SHELL'].split('/')[-1],
                             "priority": 0,
                             "estimatedTime": 1,
                             "estimatedMemory": 10,
                             "excludedHosts": "" }

        jobs = []
        # iterate over all jobs in job_list
        # update default dict by values given job
        for idx,job in enumerate(job_list):
            job_dict = copy( default_job_dict )
            job_dict.update( job )

            if job_dict['command']:
                jobs.append( job_dict )
            
            # add maximal 100 jobs in a single request
            if idx>0 and idx % 99 == 0:
                # add jobs
                jsonObj = json.dumps( jobs )

                response = self.sendAndRecv( 'addjobs:%s' % jsonObj )

                if self.verboseMode:
                    print response
                    
                jobs = []

        if jobs:
            jsonObj = json.dumps( jobs )
            
            response = self.sendAndRecv( 'addjobs:%s' % jsonObj )

            if self.verboseMode:
                print response
