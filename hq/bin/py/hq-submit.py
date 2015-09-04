#!/usr/bin/env python

PROG = "hq-submit"

import sys
import socket
import os
import pwd
from string import join, letters, digits
from random import choice
import argparse
import json
import time
import traceback
import exceptions
import subprocess
import re
import textwrap
import time
from pprint import pprint as pp
from copy import copy
import getpass

# logging
import logging
logger = logging.getLogger( PROG )
logger.propagate = False
logger.setLevel(logging.ERROR)			# logger level. can be changed with command line option -v

formatter = logging.Formatter('[%(asctime)-15s] %(message)s')

# create console handler and configure
consoleLog = logging.StreamHandler(sys.stdout)
consoleLog.setLevel(logging.INFO)		# handler level. 
consoleLog.setFormatter(formatter)

# add handler to logger
logger.addHandler(consoleLog)

HOMEDIR = os.environ['HOME']

# import hq libraries
from hq.lib.hQUtils import SmartFormatter
from hq.lib.hQSocket import hQSocket
from hq.lib.hQServerProxy import hQServerProxy
from hq.lib.hQServerDetails import hQServerDetails

# get stored host and port from taskdispatcher
hqUserServerDetails = hQServerDetails('hq-user-server')

HOST = hqUserServerDetails.get('host', None)
PORT = hqUserServerDetails.get('port', None)


if __name__ == '__main__':
    loginShell = os.environ['SHELL'].split('/')[-1]

    defaultValues = { "slots": 1,
                      "group": "",
                      "infoText": "",
                      "logfile": "",
                      "stdout": "",
                      "stderr": "",
                      "shell": loginShell,
                      "priority": 0,
                      "estimatedTime": 1,
                      "estimatedMemory": 10,
                      "excludedHosts": "" }

    helpJobsFile  = []
    helpJobsFile += ["**File in which a command line job and respective additional info are given in each line. Each line is tab-delimited with one or more properties"]
    [ helpJobsFile.append( '     {p}::<{d}>'.format(p=prop,
                                                    d=defaultValues[ prop ] ) ) for prop in sorted(defaultValues) ]
    helpJobsFile.append( "Values are separated by '::', respectively. Default values are given above." )
    helpJobsFile = '\n'.join( helpJobsFile )
    

    textWidth = 80
    parser = argparse.ArgumentParser(
        prog = PROG,
        usage = "%(prog)s [-h --help] [options] COMMAND",
        formatter_class=SmartFormatter,#argparse.RawDescriptionHelpFormatter,
        description="Submit jobs to the hq-server.",
        epilog='Written by Hendrik.')
    
    parser.add_argument('command',
                        nargs = '*',
                        metavar = 'COMMAND',
                        help = "Command which will be executed in the cluster." )    
    parser.add_argument("-c", "--slots",
                        metavar = "SLOTS",
                        dest = "slots",
                        type = int,
                        default = defaultValues['slots'],
                        help = "Number cores on a host which will be used for this job." )
    parser.add_argument("-E", "--excludeHosts",
                        metavar = "HOST[,HOST,...]",
                        dest = "excludedHosts",
                        default = defaultValues['excludedHosts'],
                        help = "Exclude computers from cluster for calculating given job. Consider option -H for a cluster overview." )
    parser.add_argument("-f", "--jobsFile",
                        metavar = "FilE",
                        default = "",
                        dest = "jobsFile",
                        help = helpJobsFile
                        )
    parser.add_argument("-g", "--group",
                        dest="group",
                        default=defaultValues["group"],
                        help="Assign a group name jobs in order to refer to them later.")
    parser.add_argument("-i", "--info-text",
                        dest="infoText",
                        default="",
                        help="Assign an info text to current job.")
    parser.add_argument("-l", "--logfile",
                        metavar="FILE",
                        dest="logfile",
                        default=defaultValues['logfile'],
                        help="Write log messages in FILE.")
    parser.add_argument("-m", "--estimatedMemory",
                       dest = "estimatedMemory",
                       default = defaultValues['estimatedMemory'],
                       help = "Specify estimated memory consumtion of job in MB.")
    parser.add_argument("-o", "--stdout_file",
                        metavar="FILE",
                        dest="stdout",
                        default=defaultValues['stdout'],
                        help="Write output of command in FILE.")
    parser.add_argument("-O", "--stderr_file",
                       metavar="FILE",
                       dest="stderr",
                       default=defaultValues['stderr'],
                       help="Write error output of command in FILE.")
    parser.add_argument("-p", "--priority",
                       dest = "priority",
                       default = defaultValues['priority'],
                       help = "Set priority of job. Higher values indicate higher priority. Max priority is 127.")
    parser.add_argument("-q", "--quiet",
                       action="store_true",
                       dest="quiet",
                       default=False,
                       help="Do not print any status messages to stdout.")
    parser.add_argument("-s", "--status",
                       action="store_true",
                       dest="showStatus",
                       default=False,
                       help="Show information about taskmanager server and taskdispatcher.")
    parser.add_argument("-S", "--shell",
                       dest = "shell",
                       default = loginShell,
                       choices = ['tcsh','bash'],
                       help = "Define execution shell (tcsh or bash). Default: {shell}.".format(shell=loginShell))
    parser.add_argument("-t", "--estimatedTime",
                       dest = "estimatedTime",
                       default = defaultValues['estimatedTime'],
                       help = "Specify estimated run time of job")
    parser.add_argument("-v", "--verbose",
                       action = "store_true",
                       dest = "verboseMode",
                       default = False,
                       help = "Print additional information to stdout.")
    
    args = parser.parse_args()

    # create HOMEDIR/.hq directory
    hqDir = "{home}/.hq".format( home=HOMEDIR )

    if not os.path.exists( hqDir ):
        os.makedirs( hqDir )

    ####################################
    # send requests to hq-user-server
    
    args.command = join(args.command,' ')

    hqUserServer = hQServerProxy( serverType = 'user-server',
                                  verboseMode = args.verboseMode )
    
    hqUserServer.run()
    
    if not hqUserServer.running:
        sys.stderr.write("Could not start a hq-user-server!\n")
        sys.exit(-1)

    requests = []
    
    # assembl requests
    if args.showStatus:
        requests = ['status']
    else:
        if args.jobsFile:
            # send several jobs at once
            jsonObj = {}

            with open(args.jobsFile,'r') as f:
                jobs = []
                
                # known job properties
                properties = [ "command" ] + defaultValues.keys()
                
                # construct regular expressions
                reProperties = { prop: re.compile( "^{prop}::(.*)$".format(prop=prop) ) for prop in properties }

                # iterate over all lines in file. add only 100 jobs at once
                for idx,line in enumerate(f):
                    line = line.strip('\n')
                    
                    try:
                        # neglect lines with a leading '#' and empty lines
                        if line and (line[0] == '#' or line==""): continue
                        
                        # parse line
                        lineSplitted = line.split( '\t' )

                        jobDetails = copy( defaultValues )
                        for entry in lineSplitted:
                            
                            # get matching property for each entry
                            try:
                                propertyName = next( propName for propName, reProp in reProperties.iteritems() if reProp.match( entry ) )
                                propertyValue, = reProperties[propertyName].match( entry ).groups( 1 )
                                
                                # replace '{idx}' by idx
                                propertyValue = propertyValue.format( idx=idx )
                                
                                jobDetails[ propertyName ] = propertyValue
                            except StopIteration:
                                pass

                        # at least command has to be specified
                        if jobDetails['command']:
                            jobs.append( jobDetails )
                                
                    except:
                        # read next row
                        traceback.print_exc(file=sys.stdout)
                        continue
                    
                    # add maximal 100 jobs in a single request
                    if idx>0 and idx % 99 == 0:
                        # add jobs
                        jsonObj = json.dumps( jobs )
                        requests.append( 'addjobs:%s' % jsonObj )
                        jobs = []

            if jobs:
                jsonObj = json.dumps( jobs )
                requests.append( 'addjobs:%s' % jsonObj )

        else:
            # send a single job
            jsonObj = {'command': args.command,
                       'slots': args.slots,
                       'infoText': args.infoText,
                       'group': args.group,
                       'stdout': args.stdout,
                       'stderr': args.stderr,
                       'logfile': args.logfile,
                       'shell': args.shell,
                       'priority': args.priority,
                       'estimatedTime': args.estimatedTime,
                       'estimatedMemory': args.estimatedMemory,
                       'excludedHosts': args.excludedHosts
                       }

            jsonObj = json.dumps(jsonObj)

            requests.append('addjob:%s' % jsonObj)

    #send commands to server
    try:
        for i,job in enumerate(requests):
            try:
                hqUserServer.send(job)
                recv = hqUserServer.recv()
                
                # print response
                if not args.quiet:
                    print recv
            except:
                traceback.print_exc(file=sys.stdout)

        #hqUserServer.sendAndRecv("unsetpersistent")
        #TMS.close()
        
    except socket.error,msg: 
        print "ERROR while connecting to hq-user-server:",msg

    sys.exit(0)
