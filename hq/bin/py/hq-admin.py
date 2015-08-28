#!/usr/bin/env python

PROG = "hq-admin"

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

# import hq libraries
from lib.hQSocket import hQSocket
from lib.hQServerDetails import hQServerDetails

# get stored host and port from taskdispatcher
hqDetails = hQServerDetails('hq-server')

hqHost = hqDetails.get('host', None)
hqPort = hqDetails.get('port', None)

# create tuple like object with field host and port
HostAndPort = collections.namedtuple( 'HostAndPort', ['host', 'port'])

class ValidateHostAndPort(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # print '{n} -- {v} -- {o}'.format(n=namespace, v=values, o=option_string)
        
        host, port = values

        # port number should be an int
        try:
            port = int(port)
        except:
            raise argparse.ArgumentError(self, 'invalid port number {p!r}'.format(p=port))

        # set attribute self.dest with field host and port
        setattr(namespace, self.dest, HostAndPort(host, port))
        # add another attribute
        setattr(namespace, "useHostAndPort", True)

        
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
        description='\n'.join( textwrap.wrap("Connect to connect to the hq-server", width=textWidth) +
                               ['\n'] +
                               textwrap.wrap("  host: {}".format(hqHost), width=textWidth) +
                               textwrap.wrap("  port: {}".format(hqPort), width=textWidth) +
                               ['\n'] +
                               textwrap.wrap("If you want to connect to another server, specify host and port with option -S.", width=textWidth)
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
    
    parser.add_argument('-S', '--server_settings',
                        nargs = 2,
                        metavar = ('HOST','PORT'),
                        action = ValidateHostAndPort,
                        dest = 'serverSettings',
                        default = HostAndPort(hqHost,hqPort),
                        help = 'Connect to server HOST:PORT. Default {h}:{p}'.format(h=hqHost, p=hqPort)
                        )

    parser.add_argument('-v', '--verbose_mode',
                        nargs = 0,
                        dest = 'verboseMode',
                        action = ValidateVerboseMode,
                        default = False,
                        help = 'Verbose mode'
                        )
    
    args = parser.parse_args()

    # here the the certificates should be read
    keyfile = None
    certfile = None
    ca_certs = None

    # set server host and port to which we try to connect
    host = args.serverSettings.host
    port = args.serverSettings.port

    try:
        # create socket
        client = hQSocket( catchErrors = False )

        client.initSocket( host, port )

        logger.info( "Connection to {host}:{port}".format( host=host, port=port ) )

        command = ' '.join( [args.command] + args.commandArgs )
        client.send(command)

        logger.info( "Command: {com}".format(com=command ))

        receivedStr = client.recv()

        logger.info( "Received string:")
        
        sys.stdout.write(receivedStr)
        
        if receivedStr:
            sys.stdout.write("\n")

        logger.info("Length of received string: {l}".format(l=len(receivedStr)))
            
        #if args.connectToTD or ( hasattr(args,'useHostAndPort') and args.useHostAndPort ):
        client.close()

    except socket.error,msg:
        print "ERROR while connecting to %s:%s with error %s" % (host, port, msg)
        if args.verboseMode:
            print "TRACBACK:"
            traceback.print_exc(file=sys.stdout)

