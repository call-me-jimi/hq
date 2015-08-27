#!/usr/bin/env python

PROG = "hq-client"

import socket
import getopt
import sys
from time import sleep
import re
import os
import pwd
import traceback
import argparse
import textwrap
import collections

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

# get path to hq. it is assumed that this script is in the bin/py directory of
# the hq package.
HQPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/../..') )

LIBPATH  = '%s/lib' % HQPATH		# for hq packages

# include lib path of the hq package to sys.path for loading hq packages
sys.path.insert(0,LIBPATH)

from hQSocket import hQSocket
from hQServerProxy import hQServerProxy
from hQServerDetails import hQServerDetails

# get stored host and port from taskdispatcher
hqServerDetails = hQServerDetails('hq-server')

HQ_SERVER_HOST = hqServerDetails.get('host', None)
HQ_SERVER_PORT = hqServerDetails.get('port', None)

# get stored host and port from tms
hqUserServerDetails = hQServerDetails('hq-user-server')

HQ_US_HOST = hqUserServerDetails.get('host', None)
HQ_US_PORT = hqUserServerDetails.get('port', None)


class ValidateBool(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        #print '{n} -- {v} -- {o}'.format(n=namespace, v=value, o=option_string)

        value = True if value=='True' else False

        # set attribute self.dest
        setattr(namespace, self.dest, value)

class ValidateVerboseMode(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        #print '{n} -- {v} -- {o}'.format(n=namespace, v=value, o=option_string)

        # set level of logger to INFO
        logger.setLevel( logging.INFO )
        
        # set attribute self.dest
        setattr(namespace, self.dest, True)
        
if __name__ == '__main__':
    # read default configurations from file
    
    textWidth = 80
    parser = argparse.ArgumentParser(
        prog=PROG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage="%(prog)s [-h --help] [options] [help] COMMAND",
        description='\n'.join( textwrap.wrap("Connect to your hq-user-server", width=textWidth) +
                               ['\n'] +
                               textwrap.wrap("  host: {}".format(HQ_US_HOST), width=textWidth) +
                               textwrap.wrap("  port: {}".format(HQ_US_PORT), width=textWidth) +
                               ['\n'] +
                               textwrap.wrap("and send the COMMAND to it and print response to stdout. If the hq-user-server is not running, a server will be started.")
                               ),
        epilog='Written by Hendrik.')
    
    parser.add_argument('command',
                        metavar = 'COMMAND',
                        help = "Command which will be sent to the server."
                        )
    
    parser.add_argument('commandArgs',
                        metavar = 'ARGS',
                        nargs = argparse.REMAINDER,
                        help = "Arguments of the COMMAND, e.g., help to get help about bare COMMAND."
                        )
    
    parser.add_argument('-v', '--verbose-mode',
                        nargs = 0,
                        dest = 'verboseMode',
                        action = ValidateVerboseMode,
                        default = False,
                        help = 'Verbose mode'
                        )
    
    args = parser.parse_args()

    try:
        # create HOMEDIR/.hq directory
        hqDir = "{home}/.hq".format( home=os.environ['HOME'] )
        
        if not os.path.exists( hqDir ):
            os.makedirs( hqDir )
        
        proxy = hQServerProxy( serverType = 'user-server',
                               verboseMode = args.verboseMode )
        proxy.run()

        if not proxy.running:
            sys.stderr.write("Could not start a hq-user-server!\n" )
            sys.exit(-1)

        logger.info( "Connection to {host}:{port}".format( host=proxy.host,
                                                           port=proxy.port ) )

        command = ' '.join( [args.command] + args.commandArgs )
        
        proxy.send( command )

        logger.info( "Command: {com}".format(com=command ))

        receivedStr = proxy.recv()

        logger.info( "Received string: "+receivedStr)
        
        sys.stdout.write(receivedStr)
        
        if receivedStr:
            sys.stdout.write("\n")

        logger.info("Length of received string: {l}".format(l=len(receivedStr)))
            
    except socket.error,msg:
        print "ERROR while connecting to %s:%s with error %s" % (HQ_US_HOST, HQ_US_PORT, msg)
        if args.verboseMode:
            print "TRACBACK:"
            traceback.print_exc(file=sys.stdout)

