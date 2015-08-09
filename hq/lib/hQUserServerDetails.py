import os
import ConfigParser

homedir = os.environ['HOME']
BASEDIR =  "{home}/.hq".format(home=homedir)

class hQUserServerDetails(object):
    """! @brief Details about a running hQ server"""
    def __init__(self, serverType ):
        self.server_type = serverType.lower()
        
        self.cfgFile = "{basedir}/hq-{serverType}.cfg".format( basedir = BASEDIR,
                                                               serverType = self.server_type )

        # store details 
        self.hQDetails = {}
        
        cfg = ConfigParser.SafeConfigParser()
        cfg.read( self.cfgFile )

        try:
            self.hQDetails['host'] = cfg.get( 'SETTINGS', 'host' )
            self.hQDetails['port'] = cfg.getint( 'SETTINGS', 'port' )
        except: 
            # could not read config file
            pass

            
    def get( self, key, defaultValue=None):
        """! @brief get value for key
        
        @param key (string) A key given in .info file
        @param defaultValue Return defaultValue if key is not known
        """

        return self.hQDetails.get( key, defaultValue )

        
    def save( self, settings):
        """! @brief Write settings into file

        @param settings (dict) Settings
        """
        # write host and port to file <varpath>/taskdispatcher.info
        cfg = ConfigParser.SafeConfigParser()

        cfg.add_section( 'SETTINGS' )

        for key,value in settings:
            cfg.set( 'SETTINGS', key, str(value) )

        if not os.path.exists( BASEDIR ):
            os.mkdir( BASEDIR )
            
        with open( self.cfgFile, 'w') as f:
            cfg.write( f )
        
        
        
