import os
import ConfigParser
import getpass

# import hq libraries
import lib.hQUtils as hQUtils

class hQServerDetails(object):
    """! @brief Details about a running hQ server"""
    def __init__(self, serverType ):
        """! @brief constructor

        @param serverType (string) one of the supported server type: hq-server, hq-user-server, hq-user-menial-server
        """
        self.server_type = serverType.lower()

        # set path to config file
        # distiguish betweent defferent server types
        if self.server_type=='hq-server':
            # get path to hq.
            # it is assumed that this package is in the lib directory of the hq package
            HQPATH = os.path.normpath( os.path.join( os.path.dirname( os.path.realpath(__file__) ) + '/..') )

            self.cfgFile = "{hqpath}/var/{serverType}.cfg".format( hqpath = HQPATH,
                                                                   serverType = self.server_type )
        else:
            # look in home directory of current user
            homedir = os.environ['HOME']
            BASEDIR =  "{home}/.hq".format(home=homedir)

            self.cfgFile = "{basedir}/{serverType}.cfg".format( basedir = BASEDIR,
                                                                serverType = self.server_type )

        # store details 
        self.hQServerDetails = {}
        
        cfg = ConfigParser.SafeConfigParser()
        cfg.read( self.cfgFile )

        try:
            self.hQServerDetails['host'] = cfg.get( 'SETTINGS', 'host' )
            self.hQServerDetails['port'] = cfg.getint( 'SETTINGS', 'port' )
        except: 
            # could not read config file

            # set default
            self.hQServerDetails['host'] = os.uname()[1]
            self.hQServerDetails['port'] = hQUtils.getDefaultPort( getpass.getuser() )

            
    def get( self, key, defaultValue=None):
        """! @brief get value for key
        
        @param key (string) A key given in .info file
        @param defaultValue Return defaultValue if key is not known
        """

        return self.hQServerDetails.get( key, defaultValue )

        
    def save( self, settings):
        """! @brief Write settings into file

        @param settings (dict) Settings
        """
        # write host and port to file <varpath>/taskdispatcher.info
        cfg = ConfigParser.SafeConfigParser()

        cfg.add_section( 'SETTINGS' )

        for key,value in settings:
            cfg.set( 'SETTINGS', key, str(value) )

        with open( self.cfgFile, 'w') as f:
            cfg.write( f )
        
        
        
