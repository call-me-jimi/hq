#!/usr/bin/env python
#
# hq/bin/py/hq-server - start the hq server
#

PROG = 'hq-user-server'

import sys
import argparse
import os
import textwrap
import ConfigParser
from datetime import datetime
import socket
import traceback
import pwd
import getpass

# import hq libraries
from lib.hQUserServer import hQUserServer
import lib.hQUtils as hQUtils

USER = getpass.getuser()

#####################################
if __name__ == '__main__':
    # host name
    hqHost = os.uname()[1]
    
    ### read hq config file
    defaultErrorLogFile = '/tmp/hq-user-server.{port}.err'

    # default port number is constructed from the user name
    defaultHQPort = hQUtils.getDefaultPort( USER )

    textWidth = 80
    parser = argparse.ArgumentParser(
        prog = PROG,
        usage = '%(prog)s [-h --help]  [OPTIONS]',
        formatter_class = argparse.RawDescriptionHelpFormatter,
        description = '\n'.join( textwrap.wrap("Run hq-user-server on", width=textWidth) +
                                 ['\n'] +
                                 textwrap.wrap("  host: {}".format(hqHost), width=textWidth)+
                                 textwrap.wrap("  port: {}".format(defaultHQPort), width=textWidth)+
                                 ['\n']+
                                 textwrap.wrap("By default an error logfile {f} is created. This can be changed with option -e.".format(f=defaultErrorLogFile.format(port=defaultHQPort)), width=textWidth ) ),
        epilog='Written by Hendrik.'
        )
    
    parser.add_argument( "-d", "--nonDaemonMode",
                         action="store_false",
                         dest="daemonMode",
                         default=True,
                         help="Start hq-user-cline in foreground (not as daemon).")
    parser.add_argument( '-p', '--port',
                         metavar = 'PORT',
                         dest = 'hQPort',
                         default = defaultHQPort,
                         type = int,
                         help = 'Start hq-server on PORT. Default: {port}.'.format(port=defaultHQPort) )
    parser.add_argument( '-q', '--quiet', 
                         dest = "noOutput", 
                         action = 'store_true',
                         default = False,
                         help = 'Suppress most of the outputs.' )
    parser.add_argument( '-e', '--error-log-file',
                         metavar = 'FILE',
                         dest = 'errorLogFileName',
                         default = defaultErrorLogFile,
                         help = 'Write errors (including exceptions) into FILE. You may include "{{port}}" into the file name which will be replace by the port. Default: {f}'.format(f=defaultErrorLogFile.format(port=defaultHQPort)) )
    parser.add_argument( '-v', '--verbose', 
                         dest = "verboseMode", 
                         action = 'store_true',
                         default = False,
                         help = 'Turn on verbose mode.' )

    # parse command line arguments
    args = parser.parse_args()
    
    # try to open logfile
    try:
        # add port to logfile name
        logfile = args.errorLogFileName.format(port=args.hQPort)

        if os.path.exists(logfile):
            # append to existing logfile
            logfileTDErrors = open(logfile, 'a')
        else:
            # create new logfile
            logfileTDErrors = open(logfile, 'w')
    
        logfileTDErrors.write('----------------------\n')
        logfileTDErrors.write("[%s]\n" % str(datetime.now()))
        logfileTDErrors.write('----------------------\n')
        logfileTDErrors.flush()
    
    except IOError,msg:
        traceback.print_exc(file=sys.stderr)
        sys.exit(-1)


    # run hQUserServer
    try:
        # what about the log file?
        hQ = hQUserServer( args.hQPort )

        if args.daemonMode:
            if args.verboseMode:
                print "hQUserServer has been started as daemon on {host}:{port}".format(host=TMS.host, port=TMS.port)
            hQ.start() # run as deamon
        else:
            hQ.run() # run not as daemon
    except socket.error,msg:
        sys.stderr.write("\n")
        sys.stderr.write("hQUserServer Socket Error: %s\n" % msg.message)
        traceback.print_exc(file=sys.stdout)
    except SystemExit,msg:
        sys.stderr.write("\n")
        if msg.code == 0:
            sys.stderr.write("hQUserServer exit\n")
        else:
            sys.stderr.write("hQUserServer system error: %s\n" % msg.message)
    except:
        sys.stderr.write("\n")
        sys.stderr.write("hQUserServer error: %s\n" % sys.exc_info()[0])
        traceback.print_exc(file=sys.stdout)
        #raise
        
    sys.stdout.flush()
    sys.stderr.flush()

