import re

class hQCommand( object ):
    """! @brief Command  """
    def __init__( self,
                  name,
                  regExp,
                  arguments = [],
                  permission = None,
                  fct = None,
                  help = "",
                  fullhelp = "" ):
        self.name = name
        self.arguments = arguments
        self.re = re.compile(regExp)
        self.permission = permission
        self.fct = fct
        self.help = help
        self.fullhelp = fullhelp


    def match( self, command_str ):
        """! @brief match regExp agains command_str """

        return self.re.match( command_str )


    def groups( self, command_str ):
        """! @brief return groups in regular expression """

        match = self.re.match( command_str )
        
        if match:
            return match.groups()
        else:
            return None
        
    def get_command_str( self ):
        """! @brief return command string """
        s = self.name

        for a in self.arguments:
            s += ":<{A}>".format(A=a.upper())
            
        return s
        
    def get_fullhelp( self ):
        """! @brief return fullhelp or, if not given, help """

        if self.fullhelp:
            return self.fullhelp
        else:
            return self.help
