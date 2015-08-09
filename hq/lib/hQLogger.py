import ConfigParser
import os
import sys
import logging

# get path to hq.
# it is assumed that this package is in the lib directory of the hq package
HQPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/..') )

class hQLogger( object ):
    """! @brief raw implementation for configuring output of logger
    """
    def __init__( self ):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('[%(asctime)-15s] %(message)s')

        # create console handler and configure
        consoleLog = logging.StreamHandler(sys.stdout)
        consoleLog.setLevel(logging.INFO)
        consoleLog.setFormatter(formatter)

        # add handler to logger
        self.logger.addHandler(consoleLog)

        self.logCategories = {}
        
        # load config file
        self.load()

    def load( self ):
        """! @brief load config file and configer logger

        about indication wether message of a particular category is passed to logger
        """
        
        configFileName = '{hqpath}/etc/hq-logger.cfg'.format(hqpath=HQPATH)
        parser = ConfigParser.SafeConfigParser()

        if os.path.exists( configFileName ):
            # read config file
            parser.read( configFileName )

            # remove all entries
            self.logCategories = {}

            # iterate over all categories
            for category in parser.items( 'CATEGORIES' ):
                try:
                    self.logCategories[ category[0] ] = True if category[1]=="True" else False
                except:
                    pass
        

    def write( self, msg, logCategory="default" ):
        if self.logCategories.get( logCategory, False ):
            self.logger.info( msg )


def wrapLogger( logger, prefix="", suffix="" ):
    """! @brief add prefix or suffix to logger of class hQLogger """

    def wrapper( *args, **kwargs ):
        logMsg = "{prefix}{logMsg}{suffix}".format( prefix = prefix,
                                                    logMsg = args[0],
                                                    suffix = suffix )
        newArgs = list(args)
        newArgs[0] = logMsg
        newArgs = tuple(newArgs)

        logger.write( *newArgs, **kwargs )
        
    return wrapper

