"""
authentication operations

Authentication instances are used to interact with the remote
authentication service, retreiving storage system routing information
and session tokens.

See COPYING for license information.
"""

from httplib  import HTTPSConnection, HTTPConnection
from urllib   import quote, quote_plus, urlencode
from utils    import parse_url, THTTPConnection, THTTPSConnection
from errors   import ResponseError, AuthenticationError, AuthenticationFailed
from consts   import user_agent, us_authurl, uk_authurl
from sys      import version_info
import re
import urlparse
import json


class BaseAuthentication(object):
    """
    The base authentication class from which all others inherit.
    """
    def __init__(self, username, api_key, authurl=us_authurl, timeout=15,
                 useragent=user_agent):
        self.authurl = authurl
        self.headers = dict()
        self.headers['x-auth-user'] = username
        self.headers['x-auth-key'] = api_key
        self.headers['User-Agent'] = useragent
        self.timeout = timeout
        (self.host, self.port, self.uri, self.is_ssl) = parse_url(self.authurl)
        if version_info[0] <= 2 and version_info[1] < 6:
            self.conn_class = self.is_ssl and THTTPSConnection or \
                THTTPConnection
        else:
            self.conn_class = self.is_ssl and HTTPSConnection or HTTPConnection

    def authenticate(self):
        """
        Initiates authentication with the remote service and returns a
        two-tuple containing the storage system URL and session token.

        Note: This is a dummy method from the base class. It must be
        overridden by sub-classes.
        """
        return (None, None, None)


class MockAuthentication(BaseAuthentication):
    """
    Mock authentication class for testing
    """
    def authenticate(self):
        return ('http://localhost/v1/account', None, 'xxxxxxxxx')


class Authentication(BaseAuthentication):
    """
    Authentication, routing, and session token management.
    """
    def authenticate(self):
        """
        Initiates authentication with the remote service and returns a
        two-tuple containing the storage system URL and session token.
        """
        conn = self.conn_class(self.host, self.port, timeout=self.timeout)
        #conn = self.conn_class(self.host, self.port)
        conn.request('GET', '/' + self.uri, headers=self.headers)
        response = conn.getresponse()
        response.read()

        # A status code of 401 indicates that the supplied credentials
        # were not accepted by the authentication service.
        if response.status == 401:
            raise AuthenticationFailed()

        # Raise an error for any response that is not 2XX
        if response.status // 100 != 2:
            raise ResponseError(response.status, response.reason)

        storage_url = cdn_url = auth_token = None

        for hdr in response.getheaders():
            if hdr[0].lower() == "x-storage-url":
                storage_url = hdr[1]
            if hdr[0].lower() == "x-cdn-management-url":
                cdn_url = hdr[1]
            if hdr[0].lower() == "x-storage-token":
                auth_token = hdr[1]
            if hdr[0].lower() == "x-auth-token":
                auth_token = hdr[1]

        conn.close()

        if not (auth_token and storage_url):
            raise AuthenticationError("Invalid response from the " \
                    "authentication service.")

        return (storage_url, cdn_url, auth_token)

class HubicAuthentication(BaseAuthentication):
    """
    Authentication for OVH's hubiC cloud storage service
    """
    OAUTH = "https://api.hubic.com/oauth/"
    HUBIC_API = "https://api.hubic.com/1.0/"

    def __init__(self, username, api_key, authurl, timeout=15, useragent=None):
        self.login = username
        self.password  = api_key
        self.authurl = authurl
        infos = self.authurl.split('|')
        if len(infos) < 4:
            raise AuthenticationError('You must give 3 vertical-bar separated arguments after hubic|')
        self.client_id = infos[1]
        self.client_secret = infos[2]
        self.redirect_uri = infos[3]
        self.timeout = timeout

    def _parse_error(self, resp):
        headers = dict(resp.getheaders())
        if not 'location' in headers:
            return None
        query = urlparse.urlsplit(headers['location']).query
        qs = dict(urlparse.parse_qsl(query))
        return {'error': qs['error'], 'error_description': qs['error_description']}

    def _get(self, url, params=None, headers={}):
        host, port, uri, is_ssl = parse_url(url)
        conn = HTTPSConnection(host, port, timeout=self.timeout)
        conn.request('GET', '/' + uri + ('?'+urlencode(params) if params else ''),
                     headers=headers)
        response = conn.getresponse()
        return conn, response

    def _post(self, url, data=None, headers={}):
        host, port, uri, is_ssl = parse_url(url)
        conn = HTTPSConnection(host, port, timeout=self.timeout)
        headers.update({'Content-type': 'application/x-www-form-urlencoded'})
        conn.request('POST', '/' + uri, urlencode(data) if data else None, headers)
        response = conn.getresponse()
        return conn, response

    def authenticate(self):
        c, r = self._get(
            self.OAUTH+'auth/',
            {
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'scope': 'credentials.r,account.r',
                'response_type': 'code',
                'state': ''
            }
        )
        if r.status != 200:
            raise AuthenticationFailed("Incorrect/unauthorized "
                    "HubiC client_id (%s)"%str(self._parse_error(r)))

        rdata = r.read()
        c.close()

        try:
            from lxml import html as lxml_html
        except ImportError:
            lxml_html = None

        if lxml_html:
            oauth = lxml_html.document_fromstring(rdata).xpath('//input[@name="oauth"]')
            oauth = oauth[0].value if oauth else None
        else:
            oauth = re.search(r'<input\s+[^>]*name=[\'"]?oauth[\'"]?\s+[^>]*value=[\'"]?(\d+)[\'"]?>', rdata)
            oauth = oauth.group(1) if oauth else None

        if not oauth:
            raise AuthenticationError("Unable to get oauth_id from authorization page")

        c, r = self._post(
            self.OAUTH+'auth/',
            data={
                'action': 'accepted',
                'oauth': oauth,
                'login': self.login,
                'user_pwd': self.password,
                'account': 'r',
                'credentials': 'r',

            },
        )
        c.close()

        if r.status == 302 and r.getheader('location', '').startswith(self.redirect_uri):
            query = urlparse.urlsplit(r.getheader('location')).query
            code = dict(urlparse.parse_qsl(query))['code']
        else:
            raise AuthenticationFailed("Unable to authorize client_id, invalid login/password ?")

        c, r = self._post(
            self.OAUTH+'token/',
            {
                'code': code,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code',
            },
            {
                'Authorization': 'Basic '+('{0}:{1}'.format(self.client_id, self.client_secret)
                                                    .encode('base64').replace('\n', ''))
            }
        )

        rdata = r.read()
        c.close()

        if r.status != 200:
            try:
                err = json.loads(rdata)
                err['code'] = r.status
            except Exception as e:
                err = {}

            raise AuthenticationFailed("Unable to get oauth access token, "
                                       "wrong client_id or client_secret ? (%s)"%str(err))

        oauth_token = json.loads(rdata)
        if oauth_token['token_type'].lower() != 'bearer':
            raise AuthenticationError("Unsupported access token type")

        c, r = self._get(
            self.HUBIC_API+'account/credentials/',
            headers={
                'Authorization': 'Bearer '+oauth_token['access_token']
            }
        )

        swift = json.loads(r.read())
        c.close()

        return swift['endpoint'], None, swift['token']


# vim:set ai ts=4 sw=4 tw=0 expandtab:
