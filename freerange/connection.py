"""
connection operations

Connection instances are used to communicate with the remote service at
the account level creating, listing and deleting Containers, and returning
Container instances.

See COPYING for license information.
"""

from   httplib        import HTTPSConnection, HTTPConnection
from   Queue          import Queue
from   consts         import __version__, user_agent, default_api_version
from   authentication import Authentication
import cloudfiles

# TODO: there should probably be a way of getting at the account and 
# url from the Connection class without having to pass it during 
# instantiation.

# Because HTTPResponse objects *have* to have read() called on them 
# before they can be used again ...
# pylint: disable-msg=W0612

class Connection(cloudfiles.Connection):
    """
    Manages the connection to the storage system and serves as a factory 
    for Container instances.
    """
    def __init__(self, username=None, password=None, account=None,\
            authurl=None, **kwargs):
        """
        Accepts keyword arguments for account, username, password and
        authurl. Optionally, you can omit these keywords and supply an
        Authentication object using the auth keyword.
        
        It is also possible to set the storage system API version and 
        timeout values using the api_version and timeout keyword 
        arguments respectively.
        """
        self.api_version = kwargs.get('api_version', default_api_version)
        auth = kwargs.has_key('auth') and kwargs['auth'] or None
        if not auth:
            if (username and password and (authurl or (authurl and account)
                                           or (not authurl and not account))):
                auth = Authentication(account, username, password, authurl)
            else:
                raise TypeError("Incorrect or invalid arguments supplied")
        kwargs['auth'] = auth

        cloudfiles.Connection.__init__(self, **kwargs)

    def _authenticate(self):
        """
        Authenticate and setup this instance with the values returned.
        """
        (url, self.token) = self.auth.authenticate(self.api_version)
        (self.host, self.port, self.uri, self.is_ssl) = cloudfiles.utils.parse_url(url)
        self.conn_class = self.is_ssl and HTTPSConnection or HTTPConnection
        self.http_connect()

    def http_connect(self):
        """
        Setup the http connection instance.
        """
        self.connection = self.conn_class(self.host, port=self.port)
        self.connection.set_debuglevel(self.debuglevel)
        
class ConnectionPool(cloudfiles.ConnectionPool):
    """
    A thread-safe connection pool object.
    """
    def __init__(self, account=None, username=None, password=None, \
            authurl=None, **kwargs):
        auth = kwargs.get('auth', None)
        self.timeout = kwargs.get('timeout', 5)
        self.connargs = dict(account=account, username=username, 
            password=password, authurl=authurl, auth=auth, timeout=self.timeout)
        poolsize = kwargs.get('poolsize', 10)
        Queue.__init__(self, poolsize)

if __name__ == '__main__':
    # pylint: disable-msg=C0103
    from authentication import MockAuthentication
    auth = MockAuthentication('eevans', 'eevans', 'bogus', 'http://10.0.0.4/')
    conn = Connection(auth=auth)
    containers = conn.get_all_containers()
    print auth.account
    for container in containers:
        print " \_", container.name
        print "   \_", ', '.join(container.list_objects())

# vim:set ai sw=4 ts=4 tw=0 expandtab:
