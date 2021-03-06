# ScrumDo - Agile/Scrum story management web application
# Copyright (C) 2011 ScrumDo LLC
#
# This software is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy (See file COPYING) of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA


from django import template
from datetime import date, time, datetime, timedelta

from projects.forms import ProjectForm
from projects.models import Story
from projects.access import has_write_access, has_admin_access, has_read_access
from projects.util import reduce_burndown_data
from projects.limits import personal_email_limit, org_email_limit
from django.template.defaultfilters import stringfilter
from django.conf import settings
from django.db import models
import traceback
import urllib



import re
register = template.Library()

urlfinder = re.compile('((?:https|http):\/\/[^\s<>]+)')
import logging

logger = logging.getLogger(__name__)



@register.simple_tag
def silk(name):
    return """<img class="silk_icon" src="%spinax/images/silk/icons/%s.png" />""" % (settings.SSL_STATIC_URL, name)


@register.filter("google_chart_url")
def google_chart_url(iteration_or_project):
    return _google_chart(iteration_or_project)

@register.filter("tiny_google_chart_url")
def tiny_google_chart_url(iteration_or_project):
    return _google_chart(iteration_or_project, project_size="200x50", iteration_size="200x50", label_axis="", bg_color="f6f6f6", axis_color="f6f6f6", title=True)

def _google_chart(iteration_or_project, project_size="550x120", iteration_size="550x80", label_axis="y", bg_color="ffffff", axis_color="444444", title=False):
    """Returns a URL for either a project or an iteration that corresponds to the burn up chart generated by google charts.
       The url will be to an image format. If no chart can be drawn, a 1x1 image is returned.  This should be used for quick
       summary charts, not detailed pretty ones.  We only use it in emails right now.  """
    try:
        total_points = []
        claimed_points = []
        max_val = 0
        claimed_dates = []
        claimed_values = []
        total_dates = []
        total_values = []

        # Chart Size...
        if hasattr(iteration_or_project,"slug"):
            size = project_size
            # Project charts are bigger than iteration charts.
        else:
            size = iteration_size

        # Gather up all the points_log entries.
        for log in iteration_or_project.points_log.all():
            total_points.append( [log.timestamp(), log.points_total] )
            claimed_points.append( [log.timestamp(), log.points_claimed] )
            if log.points_total > max_val:
                max_val = log.points_total

        # If we don't have enough points to draw a chart, bail.
        if len(total_points) <= 1:
            return "https://chart.googleapis.com/chart?cht=lxy&chs=1x1"

        # Remove redundant data in chart data.
        total_points = reduce_burndown_data(total_points)
        claimed_points = reduce_burndown_data(claimed_points)

        # Some helper values.
        start_date = total_points[0][0]        
        end_date = total_points[-1][0]
        
        
        start_date_s = date.fromtimestamp( start_date/1000 ).strftime('%Y-%m-%d')
        
        try:
            end_date_s = iteration_or_project.end_date.strftime('%Y-%m-%d')
            end_date = int(datetime.combine(iteration_or_project.end_date, time()).strftime("%s")) * 1000
            # logger.debug("!!!!")
            # logger.debug(end_date)
        except:                    
            end_date_s = date.fromtimestamp( end_date/1000 ).strftime('%Y-%m-%d')

        
        # logger.debug("END DATE" % end_date_s)            
        date_range = end_date - start_date

        # Create the entries for the total points series.
        for piece in total_points:
            total_dates.append( _googleChartValue(piece[0], start_date, end_date) )
            total_values.append( _googleChartValue( piece[1] ,0, max_val) )

        # Create the entries for the claimed points series.
        for piece in claimed_points:
            claimed_dates.append( _googleChartValue(piece[0], start_date, end_date) )
            claimed_values.append( _googleChartValue( piece[1] ,0, max_val) )

        if title:
            title_snippet = "chtt=%s&chts=000000,8&" %  urllib.quote(iteration_or_project.name)
        else:
            title_snippet = ""
        
        # Put it all together in google chart format.  (Docs: http://code.google.com/apis/chart/)
        data = "https://chart.googleapis.com/chart?%schf=bg,s,%s&chxr=0,0,%d&cht=lxy&chs=%s&chd=s:%s,%s,%s,%s&chxt=%s,x&chxs=0,%s,8,0,lt&chxl=1:|%s|%s&chco=9ED147,30B6EB&chm=B,eef5fb,1,0,0|B,99CBB0,0,0,0" % ( title_snippet, bg_color, max_val,size,"".join(claimed_dates), "".join(claimed_values), "".join(total_dates), "".join(total_values), label_axis, axis_color, start_date_s, end_date_s )
        #logger.debug(data)
        return data
    except:
        return "https://chart.googleapis.com/chart?cht=lxy&chs=1x1"


def _googleChartValue(val, min_val, max_val):
    """ Google charts can encode values in a 62 value range using alpha numeric characters.  This
        method does that for a given value, and a given range (min/max) of values """
    codes = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    percent = (val-min_val) / float(max_val - min_val)
    new_val = int( 61 * percent )
    return codes[ new_val ]

@register.filter("urlify2")
def urlify2(value):
    return urlfinder.sub(r'<a target="_blank" href="\1">\1</a>', value)

@register.filter("name_or_username")
def name_or_username(user):
    if user.first_name and user.last_name:
        return "%s %s" % (user.first_name, user.last_name)
    return user.username

@register.filter("probable_email")
def probable_email(user):
    """ Returns what is probably the user's email address.  Use this to get the address of a user who never
        actually verified it. """
    if len(user.email) > 0:
        return user.email
    addrs = user.emailaddress_set.all()
    for email in addrs:
        if email.verified:
            return email.email

    # no verified, no primary emails...
    if len(addrs) > 0:
        return addrs[0].email

    return ""

@register.filter
def gt(a, b):
    return a > b

@stringfilter
def link_stories(value, project):
    """ Creates links to stories in a body of text.
        Example: 'Story #4' would open up the edit window for story with local_id #4 """
    def replaceLink( value ):
        try:
            local_id = value.group(1)
            story = Story.objects.get( project=project, local_id=int(local_id) )
            return "<a class='storyLink' onclick=\"openOverlay( '/projects/project/%s/story/%d?return_type=block' ); return false;\" >%s</a>" % (project.slug, story.id, value.group(0))
        except:
            return value.group(0)

    return re.sub(r'[sS]tory #([0-9]+)', replaceLink , value)

link_stories.is_safe=True
register.filter('link_stories', link_stories)



@register.inclusion_tag("projects/iteration_list.html", takes_context=True)
def show_iterations(context, project):        
    request = context['request']
    show_more = False
    if (project.iterations.count() <= 15) or (request.GET.get("more","false")=="true"):
        # If less than 15 iterations, show them all
        iterations = project.iterations.all()
    else:
        # If too many, be selective
        show_more = True
        iterations = project.iterations.filter(  models.Q(default_iteration = True) |  # We always show the backlog.
                                        models.Q(start_date = None) | models.Q( end_date = None) | # And we show iterations without dates on either end
                                        models.Q(end_date__gt = datetime.today() - timedelta(days=30), end_date__lte = datetime.today()) | # We show past iterations within 30 days
                                        models.Q(start_date__gte = datetime.today(), start_date__lt =  datetime.today() + timedelta(days=30)) | # and future iterations within 30 days
                                        models.Q(start_date__lte = datetime.today(), end_date__gte =  datetime.today() ) # And current iterations too
                                        )
    return {'iterations':iterations, 'show_more':show_more, 'project':project, 'request':context['request']}
    



@register.inclusion_tag("projects/project_item.html", takes_context=True)
def show_project(context, project):
    return {'project': project, 'request': context['request']}

# @@@ should move these next two as they aren't particularly project-specific

@register.simple_tag
def clear_search_url(request):
    getvars = request.GET.copy()
    if 'search' in getvars:
        del getvars['search']
    if len(getvars.keys()) > 0:
        return "%s?%s" % (request.path, getvars.urlencode())
    else:
        return request.path

@register.simple_tag
def persist_getvars(request):
    getvars = request.GET.copy()
    if len(getvars.keys()) > 0:
        return "?%s" % getvars.urlencode()
    return ''

@register.tag(name="notlocked")
def isNotLocked(parser, token):
    tag_name, story = token.split_contents()
    nodelist = parser.parse(('endnotlocked',))
    parser.delete_first_token()
    return NotLockedNode(nodelist, story)

class NotLockedNode(template.Node):
    def __init__(self, nodelist, story):
        self.nodelist = nodelist
        self.story = story
    def render(self, context):
        if not context[self.story].iteration.locked:
            output = self.nodelist.render(context)
            return output
        else:
            return ""

@register.tag(name="archived")
def isArchived(parser, token):
    tag_name, project = token.split_contents()
    nodelist = parser.parse(('endarchived',))
    parser.delete_first_token()
    return ArchivedNode(nodelist, project)

class ArchivedNode(template.Node):
    def __init__(self, nodelist, project):
        self.nodelist = nodelist
        self.project = project
    def render(self, context):
        try:
            if not context[self.project].active:
                output = self.nodelist.render(context)
                return output
            else:
                return ""
        except:
            return ""



@register.tag(name="locked")
def istLocked(parser, token):
    tag_name, story = token.split_contents()
    nodelist = parser.parse(('endlocked',))
    parser.delete_first_token()
    return LockedNode(nodelist, story)

class LockedNode(template.Node):
    def __init__(self, nodelist, story):
        self.nodelist = nodelist
        self.story = story
    def render(self, context):
        if context[self.story].iteration.locked:
            output = self.nodelist.render(context)
            return output
        else:
            return ""

@register.tag(name="isadmin")
def isadmin( parser, token):
    tag_name, project = token.split_contents()
    nodelist = parser.parse(('endisadmin',))
    parser.delete_first_token()
    return IsAdminNode(nodelist, project)

class IsAdminNode(template.Node):
    def __init__(self, nodelist, project):
        self.nodelist = nodelist
        self.project = project
    def render(self, context):
        if has_admin_access(context[self.project], context["request"].user):
            output = self.nodelist.render(context)
            return output
        else:
            return ""

@register.tag(name="canemail")
def can_email(parser, token):
    tag_name, project = token.split_contents()
    nodelist = parser.parse(('endcanemail',))
    parser.delete_first_token()
    return CanEmailNode(nodelist, project)

class CanEmailNode(template.Node):
    def __init__(self, nodelist, project):
        self.nodelist = nodelist
        self.project = project
    def render(self, context):
        access = True
        project = context[self.project]
        if project.organization:
            access = org_email_limit.increaseAllowed(organization=project.organization)
        else:
            access = personal_email_limit.increaseAllowed(project=project)

        if access:
            output = self.nodelist.render(context)
            return output
        else:
            return ""

@register.tag(name="canwrite")
def canwrite( parser, token):
    tag_name, project = token.split_contents()
    nodelist = parser.parse(('endcanwrite',))
    parser.delete_first_token()
    return CanWriteNode(nodelist, project)

class CanWriteNode(template.Node):
    def __init__(self, nodelist, project):
        self.nodelist = nodelist
        self.project = project
    def render(self, context):
        if has_write_access(context[self.project], context["request"].user):
            output = self.nodelist.render(context)
            return output
        else:
            return ""


@register.tag(name="canread")
def canread( parser, token):
    tag_name, project = token.split_contents()
    nodelist = parser.parse(('endcanread',))
    parser.delete_first_token()
    return CanReadNode(nodelist, project)

class CanReadNode(template.Node):
    def __init__(self, nodelist, project):
        self.nodelist = nodelist
        self.project = project
    def render(self, context):
        if has_read_access(context[self.project], context["request"].user):
            output = self.nodelist.render(context)
            return output
        else:
            return ""
