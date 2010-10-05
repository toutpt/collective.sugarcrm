from suds.client import Client
from collective.sugarcrm import interfaces
from zope import component
from zope import interface
from Products.CMFCore.utils import getToolByName
import logging
from z3c.suds import get_suds_client
from plone.memoize import ram
from time import time
logger = logging.getLogger('collective.sugarcrm')

def session_cache_key(fun, self):
    #5 minutes
    five_minute = str(time() // (5*60))
    return five_minute

def get_entry_cache_key(fun, self, session=None, module='Contacts',  uid='',
                  select_fields=[]):
    #one hour + module + id
    one_hour = str(time() // (60*60))
    cache_key = one_hour +"-"+ module +"-"+ uid
    return cache_key

def get_module_fields_cache_key(fun, self, session=None, module="Contacts"):
    one_hour = str(time() // (60*60))
    cache_key = one_hour +"-"+ module
    return cache_key

class WebService(object):
    """Code base between normal and loggedin component"""
    
    interface.implements(interfaces.IComplexArgFactory,
                         interfaces.ISugarCRM)

    def __init__(self, context, url="", username="", password=""):
        """If context is not, you must provide url"""

        if context is not None:
            #get url
            pptool = getToolByName(context, 'portal_properties')
            url = pptool.sugarcrm.soap_url.encode('utf-8')
            username = pptool.sugarcrm.soap_username.encode('utf-8')
            password = pptool.sugarcrm.soap_password.encode('utf-8')

        self.context = context
        self.url = url
        self.username = username
        self.password = password
        self.client = get_suds_client(self.url+'?wsdl', context=context)
        #self.client = Client(self.url+'?wsdl')
        self._module_fields = {}

    def create(self, argument_type):
        """Create arguements types.
        
        How to use it:
        >>> crm = SugarCRM(None, "http://trial.sugarcrm.com/mwlcpt5183")
        >>> auth = crm.create("user_auth")
        >>> auth.user_name = "admin"
        >>> auth.password = "blabla"

        There are 120 available types on SugarCRM 6. To get types, just print
        print the suds client on current output
        """
        return self.client.create(argument_type)

    def _get_info(self, entry, name_value_list=True):
        info = {}
        if name_value_list:
            entry = entry.name_value_list
        for item in entry:
            info[item.name] = item.value
        return info

    def login(self, username, password):
        user = self.client.factory.create('user_auth')
        user.user_name = username
        user.password = password
        login = self.client.service.login(user)
        return login

    def logout(self, session):
        self.client.service.logout(session)

    @property
    @ram.cache(session_cache_key)
    def session(self):
        return self._session

    @property
    def _session(self):
        """Return the session of loggedin portal soap account"""

        utility = component.getUtility(interfaces.IPasswordEncryption)
        login = self.login(self.username, utility.crypt(self.password))
        return login.id

    def search(self, session=None, query_string='', module='Contacts', offset=0,
                      max=100):
        """search a contact or whatevery you want. The search is based on
        query_string argument and given module (default to Contacts)
        
        Return a list of dict with all the content from the response
        """
        
        if session is None:
            session = self.session

        results = self.client.service.search_by_module(session,
                                                       query_string,
                                                       [module],
                                                       offset, max)
        entry_list = results.entry_list

        infos = []
        for m in entry_list:
            for entry in m.records:
                infos.append(self._get_info(entry, name_value_list=False))

        return infos

    @ram.cache(get_entry_cache_key)
    def get_entry(self, session=None, module='Contacts',  uid='',
                  select_fields=[]):
        """get one entry identified by the uid argument. Type of entry
        is defined by the given module. Default to "Contacts"""

        return self._get_entry(session=session, module=module,uid=uid,
                               select_fields=select_fields)

    def _get_entry(self, session=None, module='Contacts',  uid='',
                  select_fields=[]):

        if session is None:
            session = self.session

        if not select_fields:
            #you can't call a cached method from an other cached method
            if module in self._module_fields:
                fields = self._module_fields[module]
            else:
                fields = self._get_module_fields(session=str(session),
                                                 module=str(module))
            select_fields = [field.name for field in fields]

        results = self.client.service.get_entry(session, module, uid,
                                                select_fields)
        (entry,) = results.entry_list

        info = self._get_info(entry)

        return info

    @ram.cache(get_module_fields_cache_key)
    def get_module_fields(self, session=None, module="Contacts"):
        return self._get_module_fields(session=session, module=module)

    def _get_module_fields(self, session=None, module="Contacts"):

        if session is None:
            session = self.session

        results = self.client.service.get_module_fields(session, module)
        module_fields = results.module_fields

        fields = [field for field in module_fields]
        self._module_fields[module] = fields

        return fields

if __name__ == "__main__":
    url="http://trial.sugarcrm.com/wbnawe7415/service/v2/soap.php"
    username = "will"
    password = "will"
    contact_firstname = "Jerald"
    account_name = "Max Holdings Ltd"

    #register password utility
    from zope.component import getGlobalSiteManager
    from collective.sugarcrm.password import Password
    gsm = getGlobalSiteManager()
    passwordUtility = Password()
    gsm.registerUtility(passwordUtility, interfaces.IPasswordEncryption)

    service = WebService(None, url=url, username=username,
                               password=password)

    sid = service.session
    print sid
    contacts = service.search(query_string=contact_firstname)
    contact = service.get_entry(uid=contacts[0]['id'])
    if not contact:
        print "ERROR can't find %s with get_entry"%contacts[0]
    else:
        print contact
    accounts = service.search(query_string=account_name, module="Accounts")
    account = service.get_entry(uid=accounts[0]['id'], module="Accounts")
    if not account:
        print "ERROR can't find %s with get_entry"%accounts[0]
    else:
        print account
