template = """@TEXT /wsgi.py
# encoding=UTF-8

# This file serves the project in production
# See http://wsgi.readthedocs.org/en/latest/

from __future__ import unicode_literals
from moya.wsgi import Application

application = Application(
    './',  # project directory
    ['local.ini', 'production.ini'],  # project settings files to load
    server='main',  # <server> tag to load
    logging='prodlogging.ini'  # logging settings
)
@TEXT /logging.ini

# This file tells moya what to do with log information it generates
# Tweak this if you want more or less log information

[logger:root]
handlers=moyaconsole

[logger:moya]
level=DEBUG

[logger:moya.startup]

[logger:moya.signal]

[logger:sqlalchemy.engine]
handlers=moyaconsole
# Change the following to DEBUG if you want to track down SQL issues
level=WARN
propagate=no

[handler:moyaconsole]
class=moya.logtools.MoyaConsoleHandler
formatter=simple
args=(sys.stdout,)

[handler:stdout]
class=StreamHandler
formatter=simple
args=(sys.stdout,)

[formatter:simple]
format=%(asctime)s:%(name)s:%(levelname)s: %(message)s
datefmt=[%d/%b/%Y %H:%M:%S]

@TEXT /prodlogging.ini
# Logging conf for production
# Only errors and request information is written to stdout

extends = logging.ini

[logger:root]
handlers=null

[logger:moya]
handlers=syslog
level=ERROR
propagate=no

[logger:moya.request]
level=INFO
handlers=syslog
propagate=no

[formatter:syslog]
format=:%(name)s:%(levelname)s: %(message)s
datefmt=[%d/%b/%Y %H:%M:%S]

[handler:syslog]
formatter = syslog
class = logging.handlers.SysLogHandler

# Most Linuxes
args = ('/dev/log',)

# OSX
# args = ('/var/run/syslog',)

# Windows
# args = ()

@TEXT /settings.ini

# This settings file is the default settings for your server
# It inherits the settings from basesettings.ini with the declaration below

extends=basesettings.ini

[project]
debug = yes
preflight = yes
log_signals = no

[autoreload]
enabled = yes
extensions = .xml
             .ini
             .py
             .html
             .txt
location = ./

{{% if project.database %}}
# an SQLite database is useful for development
[db:main]
engine = sqlite:///basic.sqlite
echo = no
default = yes
{{%- endif %}}

@TEXT /production.ini

# This file contains settings used in production (live on the web)
# It inherits settings from basesettings.ini with the declaration below

extends=basesettings.ini

[project]
debug = no
preflight = no

{{% if project.database %}}
# Change this to your production database
[db:main]
engine = sqlite:///basic.sqlite
echo = no
default = yes
{{% endif %}}


# We want caches to be persistent in production
# file caches are good, memcached is generally better in production

[cache:parser]
type = file
enabled = yes

[cache:templates]
type = file

[cache:fragment]
type = file

[cache:runtime]
type = file

@TEXT /basesettings.ini

# This file contains settings common to development and production

# -------------------------------------------------------------
# Project settings
# -------------------------------------------------------------

[settings]
project_title = ${{ project.title }}

[project]
# A randomly generated secret key used by csrf protection
secret = ${{ secret }}
# Enable debug mode
debug = yes
# Show file and line for <echo> text
debug_echo = no
# Write logs regarding signals
log_signals = no
# Run pre-flight checks before running server
preflight = yes
# Location of moya logic xml files
location = ./startup
# Path to logic file containing server
startup = server.xml

[themes]
location = ./themes

[debug]

[autoreload]
enabled = no

# -------------------------------------------------------------
# Sites
# -------------------------------------------------------------

# Default site
[site]
# Content to use if no base content is specified
base_content = site#content.base
# Default timezone to use
timezone = ${{timezone}}
# Use the timezone specified in the current user, if available
user_timezone = yes
# Append a slash to urls that 404
append_slash = yes
# set which theme file to read
theme = default

# Catch all domains for a production server
[site:{*domain}]
priority = -1
data-server = production
data-url = ${.request.host_url}

# Settings for the development server
[site:127.0.0.1,localhost]
data-domain = localhost
data-server = dev
data-url = http://localhost:8000

# An example of how to manage subdomains
#[site:${subdomain}.example.org]
#data-url = http://${subdomain}.example.org

# -------------------------------------------------------------
# Filesystems
# -------------------------------------------------------------

[fs:project]
location = ./

[fs:static]
location = ./static

# -------------------------------------------------------------
# Caches
# -------------------------------------------------------------

[cache:parser]
# Cache used to store parsed expressions
type = dict
namespace = parser
location = ./__moyacache__
enabled = no

[cache:templates]
# Cache used to store compiled templates
type = dict
namespace = templates
location = ./__moyacache__

[cache:fragment]
# Cache used to store html fragments
type = dict
namespace = framgment
location = ./__moyacache__

[cache:runtime]
# Used by <cache-return> tag to cache expensive calculations
type = dict
namespace = runtime
location = ./__moyacache__


# -------------------------------------------------------------
# Email servers
# -------------------------------------------------------------
[smtp:default]
host = 127.0.0.1
sender = ${{author.email}}


# -------------------------------------------------------------
# Media
# -------------------------------------------------------------

[media]
location = ./static


# -------------------------------------------------------------
# Templates
# -------------------------------------------------------------

[templates:default]
location = ./templates
priority = 10


# -------------------------------------------------------------
# Applications
# -------------------------------------------------------------

{{%- if project.pages %}}
[settings:pages]
autocreate = about
             contact
             privacy-policy
             terms-and-conditions
{{% endif %}}

{{%- if project.feedback %}}
[settings:feedback]
email_to = ${{author.email}}
email_from = ${{author.email}}
{{%- endif %}}

[settings:media]
fs = media
hide =
dirlist = yes
index =

[settings:diagnostics]
email_from =
admin_email = ${{author.name}} <${{author.email}}>
subject = [${.request.host}]


@WRAPTEXT /themes/readme.txt
The file(s) in this directory store theme settings.

These settings are used to customize colors and other values for a given site.

Moya loads the JSON file from the 'theme' value in the matching [site] section in the project settings file. You can then refer to the theme data as '.theme'.

@TEXT /themes/default.json
{
    "colors":
    {
        "text":
        {
            "fg": "#333",
            "bg": "white"
        },
        "highlight":
        {
            "fg": "#333",
            "bg": "#eee"
        },
        "selected":
        {
            "fg": "#fff",
            "bg": "#337ab7"
        },
        "border":
        {
            "normal": "#ccc",
            "focused": "#ddd"
        }
    }

}

@TEXT /moya
# The presence of this file indicates that this directory is a top-level moya project.
#
# The command line tool will look for this in the current directory and ancestors.
#
# Although the contents of this file are not currently read by Moya, in the future this file may be an INI file.

@WRAPTEXT /static/readme.txt
The contents of this directory will be served as static files by the moya.static library (including this file)!
If you have directory listing enabled, you can see what files are served by visiting the /static/ url in your browser.
@TEXT /data/readme.txt
Static data (typically json files) may be placed here.
@TEXT /site/lib.ini
[author]
name = ${{author.name}}
email = ${{author.email}}
url = ${{author.url}}
organization = ${{author.organization}}

[lib]
title = ${{ project.title }}
url = /
namespace =
name = site.${{slug:project.title}}
location = ./logic
version = 0.1

[locale]
location = ./locale
default_language = en
languages = en

@WRAPTEXT /site/locale/readme.txt
Internationalization files go here.

@WRAPTEXT /site/logic/readme.txt
This is the 'site' library. It should contain code/data that is specific to the project (i.e. anything that you are unlikely to reuse).

@TEXT /templates/base.html
{% extends "base.html" from "moya.twitter.bootstrap" %}
@WRAPTEXT /external/readme.txt
This folder should contain libraries that are external (i.e. authored elsewhere).
The moya command line app installs libraries to this location.

NB. If you make local edits to these files, the moya command line app may end up overwriting them!
@WRAPTEXT /templates/readme.txt
This folder contains site-wide templates, typically used to customize the look and feel of the site.
@WRAPTEXT /local/readme.txt
This folder should contain libraries that are local to the project, i.e. authored by yourself or organization.
@TEXT /startup/server.xml
<moya xmlns="http://moyaproject.com">

    <!-- Initialize a server -->
    <server docname="main">

        <!-- Import libraries for use in your project -->
        <import py="moya.libs.debug" if=".debug"/>
        <import py="moya.libs.diagnostics" if="not .debug"/>
        {{%- if project.auth %}}
        <import py="moya.libs.auth" />
        <import py="moya.libs.session" />
        {{%- endif %}}
        {{%- if project.signup %}}
        <import py="moya.libs.signup" />
        {{%- endif %}}
        <import py="moya.libs.admin" />
        <import py="moya.libs.static" />
        <import py="moya.libs.favicon" />
        <import py="moya.libs.welcome" />
        <import py="moya.libs.links" />
        <import py="moya.libs.bootstrap" />
        <import py="moya.libs.forms" />
        <import py="moya.libs.widgets" />
        {{%- if project.comments %}}
        <import py="moya.libs.comments" />
        {{%- endif %}}
        {{%- if project.pages %}}
        <import py="moya.libs.pages" />
        {{%- endif %}}
        {{%- if project.blog %}}
        <import py="moya.libs.blog" />
        {{%- endif %}}
        {{%- if project.feedback %}}
        <import py="moya.libs.feedback" />
        {{%- endif %}}
        <import py="moya.libs.jsonrpc" />
        <import py="moya.libs.wysihtml5" />
        {{%- if project.signup or project.comments %}}
        <import py="moya.libs.recaptcha" />
        {{%- endif %}}

        <!-- The 'site' library, for non reusable content -->
        <import location="./site" priority="10" />
        <install name="site" lib="site.${{slug:project.title}}" mount="/" />

        <!-- Install applications (instances of a library) -->
        <install name="forms" lib="moya.forms" />
        <install name="widgets" lib="moya.widgets" />
        {{%- if project.auth %}}
        <install name="auth" lib="moya.auth" mount="/auth/" />
        <mount app="auth" mountpoint="middleware" url="/" />
        <install name="session" lib="moya.session" mount="/" />
        {{%- endif %}}
        {{%- if project.signup %}}
        <install name="signup" lib="moya.signup" mount="/signup/"/>
        {{%- endif %}}
        <install name="admin" lib="moya.admin" mount="/admin/" />
        <install name="media" lib="moya.static" mount="/static/" />
        <install name="debug" lib="moya.debug" mount="/debug/" if=".debug"/>
        <install name="diagnostics" lib="moya.diagnostics" if="not .debug"/>
        <install name="bootstrap" lib="moya.twitter.bootstrap" />
        <install name="welcome" lib="moya.welcome" mount="/" />
        <install name="links" lib="moya.links" />
        <install name="favicon" lib="moya.favicon" mount="/" />
        {{%- if project.comments %}}
        <install name="comments" lib="moya.comments" mount="/comments/" />
        {{%- endif %}}
        {{%- if project.pages %}}
        <install name="pages" lib="moya.pages" mount="/" urlpriority="-10"/>
        {{%- endif %}}
        {{%- if project.blog %}}
        <install name="blog" lib="moya.blog" mount="/blog/" />
        {{%- endif %}}
        {{%- if project.feedback %}}
        <install name="feedback" lib="moya.feedback" mount="/feedback/" />
        {{%- endif %}}
        {{%- if project.jsonrpc %}}
        <install name="jsonrpc" lib="moya.jsonrpc" />
        {{%- endif %}}
        <install name="wysihtml5" lib="moya.wysihtml5" />
        {{%- if project.signup or project.comments %}}
        <install name="recaptcha" lib="moya.google.recaptcha" />
        {{%- endif %}}

    </server>

</moya>
@WRAPTEXT /readme.txt
Getting Started
===============

This file was created by running the command 'moya start project'. The other files in this directory contain a Moya project tailored to your requirements.

There are a few quick steps you need to run before you can begin developing your website. If you haven't already done so, open up a terminal and navigate to the same directory that contains this file.

If you opted for a database, review the database settings in 'settings.ini'. The default settings will automatically create an sqlite database in this directory.

Next, run the following to create the database and initialize any tables:

    moya init

Use the following command to run a development server:

    moya runserver

If all goes well, Moya will let you know it is serving your web site. Point your browser at http://127.0.0.1:8000 to see it.

See http://moyaproject.com/gettingstarted/ for more information.
@TEXT /site/logic/content.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let"
      xmlns:db="http://moyaproject.com/db"
      xmlns:forms="http://moyaproject.com/forms"
      xmlns:html="http://moyaproject.com/html">

</moya>
@TEXT /site/logic/models.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com">
    <!-- Here's were you might define your database models -->
    <!--
    <model name="Student" libname="Student" xmlns="http://moyaproject.com/db">
        <string name="name" length="30" />
        <string name="email" length="300" />
    </model>
    -->
</moya>
@TEXT /site/logic/views.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let"
      xmlns:db="http://moyaproject.com/db"
      xmlns:forms="http://moyaproject.com/forms">

    <!-- Views go here -->

</moya>
@TEXT /site/logic/forms.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com">

    <!-- Forms know how to render and validate themselves -->
    <form libname="form.getname" legend="Hello World Form" style="horizontal" xmlns="http://moyaproject.com/forms">
        <input name="name" label="What is your name?" class="input-xlarge" type="text" maxlength="30" required="yes"/>
        <submit-button text="Submit" />
    </form>

</moya>
@TEXT /site/logic/content.xml
<moya xmlns="http://moyaproject.com"
      xmlns:links="http://moyaproject.com/links"
      xmlns:html="http://moyaproject.com/html">

    <content libname="content.base">
        <links:get dst="navlinks" />
    </content>

</moya>

@TEXT /site/logic/data.xml
<moya xmlns="http://moyaproject.com"
      xmlns:links="http://moyaproject.com/links">
    <!-- Data tags go here -->
    <links:link text="About" from="pages" name="showpage" with="{'pagename': 'about'}" if=".apps.pages"/>
    <links:link text="Blog" from="blog" name="list" if=".apps.blog" />
    <links:link text="Contact" from="pages" name="showpage" with="{'pagename': 'contact'}" if=".apps.pages"/>
    <links:link text="Feedback" from="feedback" name="feedback" if=".apps.feedback" />
    <links:link text="Debug" from="debug" name="intro" if=".apps.debug" />
</moya>
{{% if project.jsonrpc %}}
@TEXT /site/logic/rpc.xml
<moya xmlns="http://moyaproject.com"
      xmlns:rpc="http://moyaproject.com/jsonrpc"
      xmlns:let="http://moyaproject.com/let">

    <!-- Here's an example JSONRPC interface to get you started. -->

    <!-- Use an enumeration so you can refer to error codes by a label -->
    <enum libname="enum.jsonrpc.errors">
        <value id="1" name="name_too_long">
            This error occurs when you enter a name of more than 10 characters.
        </value>
    </enum>

    <!-- This object creates a view that exposes methods via JSON RPC -->
    <rpc:interface libname="jsonrpc.interface" errors="#enum.jsonrpc.errors">

        <!-- An example of a simple remote method -->
        <rpc:method name="greet" description="Renders a greeting">
            <doc>This method will greet you, using the name of your choice</doc>
            <rpc:parameter name="who" type="string" default="'World'" required="no">
                This parameter should be the name of the person you wish to greet. If not given, the name will default to "World"
            </rpc:parameter>
            <rpc:error code="name_too_long" if="len:who gt 10" data="errortext='What were you thinking?',foo='bar'">
                'who' should be ten characters or less, not '${who}'
            </rpc:error>
            <return>
                <str>Hello, ${who}!</str>
            </return>
        </rpc:method>

    </rpc:interface>


</moya>
{{% endif %}}
@WRAPTEXT /site/logic/readme.txt
XML files go in here.

The filenames used here are just a suggestion of how to organize your Moya code -- all files with the extension .xml will be read.
@TEXT /site/logic/mountpoints.xml
<moya xmlns="http://moyaproject.com">

    <!-- Libraries will typically define a mountpoint to add URLs -->
    <mountpoint name="main">
        {{%- if project.jsonrpc %}}
        <!-- The view for your JSON Remote Procedure Call interface -->
        <url route="/jsonrpc/" methods="GET,POST" view='#jsonrpc.interface' name="jsonrpc" />
        {{%- endif %}}
    </mountpoint>

</moya>
@WRAPTEXT /site/readme.txt
This folder contains the 'site' library. The site library is for functionality that is highly specific to the site, and is generally used to customize functionality of other libraries.
@WRAPTEXT /startup/readme.txt
This folder contains the first XML files read by Moya, which will typically contain one or more <server> declarations.
@TEXT /templates/email/base.txt
{# You can customize email text templates here %}
{%- block "content" %}{% endblock -%}
--
${.settings.project_title}
@TEXT /templates/email/base.html
{#
    By convention, Moya's (html) email templates extend from this template.

    You can theme all default emails by modfying this template.
#}
{%- block "content" %}{% endblock -%}
<p>--</p>
<p>${.settings.project_title}</p>
"""
