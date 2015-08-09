#!/usr/bin/env python
#
# hq/bin/py/hq-server - start the hq server
#

PROG = 'hq-server'

import sys
import argparse
import os
import textwrap
import ConfigParser
from datetime import datetime
import socket
import traceback

# get path to hq.
# it is assumed that this package is in the bin/py directory of the hq package
HQPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/../..' ) )

ETCPATH  = '%s/etc' % HQPATH		# for configuration files
LIBPATH  = '%s/lib' % HQPATH		# for hq packages

# include lib path of the hq package to sys.path for loading hq packages
sys.path.insert(0,LIBPATH)

from hQServer import hQServer


#####################################
if __name__ == '__main__':
    # host name
    hQHost = os.uname()[1]
    
    # read hq config file
    hQConfigFileName = "%s/hq-server.cfg" % ETCPATH
    
    hQConfig = ConfigParser.ConfigParser()
    hQConfig.read( hQConfigFileName )

    defaultHQPort = hQConfig.getint( 'ADDRESS', 'hQServerPort' )
        
    defaultErrorLogFile = '/tmp/hq-server.{port}.err'

    textWidth = 80
    parser = argparse.ArgumentParser(
        prog = PROG,
        usage = '%(prog)s [-h --help] [OPTIONS]',
        formatter_class = argparse.RawDescriptionHelpFormatter,
        description = '\n'.join( textwrap.wrap("Run hq-server on", width=textWidth) +
                                 ['\n'] +
                                 textwrap.wrap("  host: {}".format(hQHost), width=textWidth)+
                                 textwrap.wrap("  port: {}".format(defaultHQPort), width=textWidth)+
                                 ['\n']+
                                 textwrap.wrap("By default an error logfile {f} is created. This can be changed with option -e.".format(f=defaultErrorLogFile.format(port=defaultHQPort)), width=textWidth ) ),
        epilog='Written by Hendrik.'
        )
    
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


    # run hQServer
    try:
        # what about the log file?
        hQ = hQServer( args.hQPort )

        hQ.run() # run not as daemon;
    except socket.error,msg:
        sys.stderr.write("\n")
        sys.stderr.write("hQServer Socket Error: %s\n" % msg.message)
        traceback.print_exc(file=sys.stdout)
    except SystemExit,msg:
        sys.stderr.write("\n")
        if msg.code == 0:
            sys.stderr.write("hQServer exit\n")
        else:
            sys.stderr.write("hQServer system error: %s\n" % msg.message)
    except:
        sys.stderr.write("\n")
        sys.stderr.write("hQServer error: %s\n" % sys.exc_info()[0])
        traceback.print_exc(file=sys.stdout)
        #raise
        
    sys.stdout.flush()
    sys.stderr.flush()

