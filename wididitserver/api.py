# Copyright (C) 2011, Valentin Lorentz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.conf.urls.defaults import patterns, include, url
from django.core.context_processors import csrf
from django.http import HttpResponse

from piston.authentication import OAuthAuthentication, HttpBasicAuthentication
from piston.handler import BaseHandler, AnonymousBaseHandler
from piston.resource import Resource
from piston.utils import validate
from piston.utils import rc

from wididit import constants
from wididit import utils

from wididitserver.models import Server, People, Entry, User
from wididitserver.models import ServerForm, PeopleForm, EntryForm
from wididitserver.utils import settings


##########################################################################
# Utils

auth = HttpBasicAuthentication(realm='Wididit server')
#auth = OAuthAuthentication(realm='Wididit server')

def get_server(hostname=None):
    if hostname is None:
        hostname = settings.WIDIDIT_HOSTNAME
    return Server.objects.get(hostname=hostname)

def get_user(usermask):
    username, servername = utils.usermask2tuple(usermask,
            settings.WIDIDIT_HOSTNAME)
    server = get_server(servername)
    return People.objects.get(username=username, server=server)


##########################################################################
# Server

class AnonymousServerHandler(AnonymousBaseHandler):
    allowed_methods = ('GET',)
    model = Server
    fields = ('self', 'hostname',)

    def read(self, request):
        """Returns the list of servers this server is connected to.

        See :ref:`concept-network`.
        """
        return Server.objects.all()

class ServerHandler(BaseHandler):
    anonymous = AnonymousServerHandler
    model = anonymous.model
    fields = anonymous.fields

    def read(self, request):
        return self.anonymous().read(request)

server_handler = Resource(ServerHandler, authentication=auth)


##########################################################################
# People

class AnonymousPeopleHandler(AnonymousBaseHandler):
    allowed_methods = ('GET', 'POST',)
    model = People
    fields = ('username', 'server',)

    def read(self, request, usermask=None):
        """Returns either a list of all people registered, or the
        user matching the username (wildcard not allowed)."""
        if usermask is None:
            return People.objects.all()
        else:
            try:
                username, servername = utils.usermask2tuple(usermask,
                        settings.WIDIDIT_HOSTNAME)
                print repr(username)
                print repr(servername)
                server = get_server(servername)
                obj = People.objects.get(username=username, server=server)
                return obj
            except People.DoesNotExist:
                return rc.NOT_FOUND
            except Server.DoesNotExist:
                return rc.NOT_FOUND

    @validate(PeopleForm, 'POST')
    def create(self, request):
        data = request.form.cleaned_data
        user = User.objects.create_user(data['username'], data['email'],
                data['password'])
        user.save()
        people = request.form.save()
        people.user = user
        people.server = get_server()
        people.save()
        return rc.CREATED

class PeopleHandler(BaseHandler):
    allowed_methods = ('GET', 'POST', 'PUT',)
    anonymous = AnonymousPeopleHandler
    model = anonymous.model
    fields = anonymous.fields

    @validate(PeopleForm, 'PUT')
    def update(self, request, usermask):
        username, servername = utils.usermask2tuple(usermask,
                settings.WIDIDIT_HOSTNAME)
        if servername != settings.WIDIDIT_HOSTNAME:
            # Want to change the password on another server?
            return rc.BAD_REQUEST
        data = request.form.cleaned_data
        if username != request.user.username:
            # Don't allow to edit other's account
            return rc.FORBIDDEN
        if username != data['username']:
            # We don't allow username changes
            return rc.FORBIDDEN
        request.user.set_password(data['password'])
        request.user.save()
        return rc.ALL_OK

people_handler = Resource(PeopleHandler, authentication=auth)


##########################################################################
# Entry

class AnonymousEntryHandler(AnonymousBaseHandler):
    allowed_methods = ('GET',)
    model = Entry

    def read(self, request, usermask=None, id=None):
        """Returns either a list of notices (either from everybody if
        `usermask` is not given, either from the `usermask`) or an entry if
        `usermask` AND `id` are given."""
        if usermask is not None:
            username, servername = utils.usermask2tuple(usermask,
                    settings.WIDIDIT_HOSTNAME)
            try:
                server = get_server(servername)
                user = People.objects.get(username=username, server=server)
            except User.DoesNotExist:
                return rc.NOT_FOUND
            except Server.DoesNotExist:
                return rc.NOT_FOUND

        if usermask is None and id is None:
            # FIXME: limit this to a fixed number of results
            return Entry.objects.all()
        elif id is None: # and author is not None
            return Entry.objects.filter(author=user)
        else:
            assert id is not None and author is not None
            try:
                return Entry.objects.get(author=user, id=id)
            except Entry.DoesNotExist:
                return rc.NOT_FOUND

class EntryHandler(BaseHandler):
    allowed_methods = ('GET', 'POST',)
    anonymous = AnonymousEntryHandler
    model = anonymous.model

    @validate(EntryForm, 'POST')
    def create(self, request, usermask):
        username, hostname = utils.usermask2tuple(usermask,
                settings.WIDIDIT_HOSTNAME)
        if hostname != settings.WIDIDIT_HOSTNAME:
            # Want to change the password on another server?
            return rc.NOT_IMPLEMENTED
        user = People.objects.get(user=request.user)
        if user != get_user(usermask):
            return rc.FORBIDDEN
        data = request.form.cleaned_data
        entry = request.form.save(commit=False)
        entry.author = user
        entry.save()
        return rc.CREATED

entry_handler = Resource(EntryHandler, authentication=auth)

urlpatterns = patterns('',
    url(r'^server/$', server_handler, name='wididit:server_list'),
    url(r'^people/$', people_handler, name='wididit:people_list'),
    url(r'^people/(?P<usermask>%s)/$' % constants.USER_MIX_REGEXP, people_handler, name='wididit:show_people'),
    url(r'^entry/$', entry_handler, name='wididit:entry_list_all'),
    url(r'^entry/(?P<usermask>%s)/$' % constants.USER_MIX_REGEXP, entry_handler, name='wididit:entry_list_author'),
    url(r'^entry/(?P<usermask>%s)/(?P<id>[0-9]+)/$' % constants.USER_MIX_REGEXP, entry_handler, name='wididit:show_entry'),
    url(r'^entry/(?P<usermask>%s)/(?P<id>[0-9]+)/$' % constants.USER_MIX_REGEXP, entry_handler, name='wididit:show_entry'),
)
