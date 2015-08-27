#!/usr/bin/env python
#
# hq/bin/py/hq-dbadmin - administrate database
#

PROGNAME = "hq-dbadmin"

import sys
import os
import argparse
import textwrap
import sqlalchemy
import ConfigParser
from sqlalchemy.orm.exc import NoResultFound
from datetime import datetime
import traceback


# logging
import logging
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.ERROR)			# logger level. can be changed with command line option -v

formatter = logging.Formatter('[%(asctime)-15s] %(message)s')

# create console handler and configure
consoleLog = logging.StreamHandler(sys.stdout)
consoleLog.setLevel(logging.INFO)		# handler level. 
consoleLog.setFormatter(formatter)

# add handler to logger
logger.addHandler(consoleLog)


# get path to config file. it is assumed that this progran is in the bin/py directory of
# the package hierarchy.
ETCPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/../../etc' ) )
LIBPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/../../lib' ) )

sys.path.insert(0,LIBPATH)

from hQPingHost import hQPingHost

class ValidateVerboseMode(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        #print '{n} -- {v} -- {o}'.format(n=namespace, v=value, o=option_string)

        # set level of logger to INFO
        logger.setLevel( logging.INFO )
        
        # set attribute self.dest
        setattr(namespace, self.dest, True)
        
if __name__ == '__main__':
    textWidth = 80
    parser = argparse.ArgumentParser(
        prog=PROGNAME,
        usage="%(prog)s [-h --help] [options]",
        description="Connect to a database",
        epilog='Written by Hendrik.' )

    ##parser.add_argument('-c', '--config-file',
    ##                    nargs = 1,
    ##                    metavar = "FILE",
    ##                    dest = 'configFileName',
    ##                    default = defaultConfigFileName,
    ##                    help = 'Read a different config file. Default: {f}'.format(f=defaultConfigFileName)
    ##                    )

    parser.add_argument('-C', '--create-tables',
                        dest = 'createTables',
                        action = 'store_true',
                        default = False,
                        help = 'Create all tables in database.'
                        )

    parser.add_argument('-D', '--drop-tables',
                        dest = 'dropTables',
                        action = 'store_true',
                        default = False,
                        help = 'Drop all tables in database.'
                        )

    parser.add_argument('-s', '--show-database-configuration',
                        dest = 'showDatabaseConfig',
                        action = 'store_true',
                        default = False,
                        help = 'Show database configuration.'
                        )
    
    parser.add_argument('-v', '--verbose-mode',
                        nargs = 0,
                        dest = 'verboseMode',
                        action = ValidateVerboseMode,
                        default = False,
                        help = 'Activate verbose mode.'
                        )
    
    parser.add_argument('-a', '--add-standard-entries',
                        dest = 'add_standard_entries',
                        action = 'store_true',
                        default = False,
                        help = 'Adds standard entries to tables in database.')
    
    args = parser.parse_args()


    logger.info( "Welcome to {p}!".format(p=PROGNAME) )

    configFileName = "%s/hq-db.cfg" % ETCPATH
    
    logger.info( "Reading config file {f}".format(f=configFileName) )
    
    # read config file
    if os.path.exists( configFileName ):
        config = ConfigParser.ConfigParser()
        config.read( configFileName )
    else:
        sys.stderr.write( "ERROR: Could not find Config file {c}!".format( c=configFileName) )
        sys.exit( -1 )

    if args.showDatabaseConfig:
        databaseDialect = config.get( 'DATABASE', 'database_dialect' )
        databaseHost = config.get( 'DATABASE', 'database_host' )
        databasePort = config.get( 'DATABASE', 'database_port' )
        databaseName = config.get( 'DATABASE', 'database_name' )
        databaseUsername = config.get( 'DATABASE', 'database_username' )
        databasePassword = config.get( 'DATABASE', 'database_password' )

        print "Database configuration:"
        print
        print "{k:>20} : {v}".format( k='database_dialect', v=databaseDialect )
        print "{k:>20} : {v}".format( k='database_host', v=databaseHost )
        print "{k:>20} : {v}".format( k='database_port', v=databasePort )
        print "{k:>20} : {v}".format( k='database_name', v=databaseName )
        print "{k:>20} : {v}".format( k='database_username', v=databaseUsername )
        print "{k:>20} : {v}".format( k='database_password', v=databasePassword )

    elif args.createTables:
        # This will not re-create tables that already exist.

        logger.info( "Create tables in database" )

        #from DBConnection import DBConnection
        #session = DBConnection()
        #session.create_all_tables()

        # import registry to define another engine with echo=True
        import hQDBSessionRegistry as dbSessionReg
        dbSessionReg.init_db( dbSessionReg.get_engine(echo=True) )
        
        logger.info( "done." )

    elif args.dropTables:
        # This will really drop all tables including their contents.

        answer = raw_input( "Are you sure you want to drop all tables in '{dbName}' [y|N]? ".format(dbName=config.get( 'DATABASE', 'database_name' )) )
        if answer=='y':
            logger.info( "Drop tables in database" )
            
            from hQDBConnection import hQDBConnection
            
            session = hQDBConnection()
            
            session.drop_all_tables()
            
            logger.info( "done." )
        else:
            logger.info( "Nothing has been done." )

    if args.add_standard_entries:
        # This will add standard entries to tables in database
        logger.info( "Add standard entries" )
        
        from hQDBConnection import hQDBConnection
        import hQDatabase as db

        con = hQDBConnection()

        users = {}
        # read users and roles from file
        #    <USER1>   <ROLE1>,<ROLE2>,...
        #    ...
        if os.path.exists('%s/users' % ETCPATH):
            with open('%s/users' % ETCPATH) as f:
                users = map(lambda l: l.strip().split('\t'), f.readlines())
                users = { e[0]: set( e[1].split(",") ) for e in users }
        else:
            users = {}

        for user in users:
            try:
                userInstance = con.query( db.User ).filter( db.User.name==user ).one()
            except NoResultFound:
                # add user
                logger.info( "Add User {name}".format(name=user) )

                userInstance = db.User( name=user )

            # get already associated roles
            assocRoleNames = set( [r.role.name for r in userInstance.roles ] )
            
            # check roles
            for role in users[ user ]:
                if role not in assocRoleNames:
                    # create new association
                    newAssoc = db.AssociationUserRole()
                    
                    # get role if existing
                    try:
                        roleInstance = con.query( db.Role ).filter( db.Role.name==role ).one()
                    except NoResultFound:
                        # add user
                        logger.info( "Add Role {name}".format(name=role) )

                        roleInstance = db.Role( name=role )

                    # add role to association
                    newAssoc.role = roleInstance

                    # add association to user
                    userInstance.roles.append( newAssoc )
                    
                con.introduce( userInstance )
        con.commit()


        # fill JobStatus table
        js = [ 'waiting', 'pending', 'running', 'finished' ]
        for jobStatus in js:
            try:
                con.query( db.JobStatus ).filter( db.JobStatus.name==jobStatus ).one()
            except NoResultFound:
                logger.info( "Add entry '{j}' to JobStatus table.".format(j=jobStatus ) )
                
                jobStatusInstance = db.JobStatus( name=jobStatus )
                
                con.introduce( jobStatusInstance )
        con.commit()


        # read cluster table
        try:
            tableFileName = '{etcpath}/cluster.tab'.format(etcpath=ETCPATH)
            
            if os.path.exists( tableFileName ):
                with open( tableFileName ) as f:
                    # skip first line
                    f.readline()

                    # iterate over all lines
                    for line in f:
                        line = line.strip("\n")
                        lineSplitted = line.split("\t")

                        if len(line)>0 and len(lineSplitted)==8:
                            defaultSettings = { 'full_name': '',
                                                'short_name': '',
                                                'total_number_slots': 0,
                                                'max_number_occupied_slots': 0,
                                                'additional_info': '',
                                                'allow_info_server': False,
                                                'info_server_port': 0 }
                            defaultStatus = { 'active': False }
                            
                            # columns: short_name, full_name, total_number_slots, max_number_occupied_slots, additional_info, allow_info_server, info_server_port, active
                            settings = dict( filter( lambda s: s[1]!="", zip( ["short_name",
                                                                               "full_name",
                                                                               "total_number_slots",
                                                                               "max_number_occupied_slots",
                                                                               "additional_info",
                                                                               "allow_info_server",
                                                                               "info_server_port",
                                                                               "active"], lineSplitted ) ) )

                            # get host setting using dict comprehension, prefer settings from settings file
                            # automatically cast value to type of value given in defaultSettings
                            hostSettings = { key: type(defaultValue)(settings.get(key, defaultValue)) for key,defaultValue in defaultSettings.iteritems() }
                            hostStatus = { key: type(defaultValue)(settings.get(key, defaultValue)) for key,defaultValue in defaultStatus.iteritems() }

                            # add entry in database if not already present
                            try:
                                con.query( db.Host ).filter( db.Host.full_name==hostSettings['full_name'] ).one()
                            except NoResultFound:
                                logger.info( "Add Host {name} to cluster".format(name=hostSettings['short_name'] ) )

                                # create entry in database
                                host = db.Host( **hostSettings )

                                ph = hQPingHost( hostSettings['full_name'] )
                                ph.start()
                                ph.join()

                                reachable = False
                                if ph.status[1]>0:	# ph.status: (transmitted,received)
                                     # successful ping
                                     reachable = True


                                # create HostSummaryInstance
                                hostSummary = db.HostSummary( host=host,
                                                              available=hostStatus['active'],
                                                              reachable=reachable )

                                con.introduce( host, hostSummary )
                con.commit()

        except:
            traceback.print_exc(file=sys.stdout)
            pass


    logger.info( "Thank you for using {p}!".format( p=PROGNAME ) )



