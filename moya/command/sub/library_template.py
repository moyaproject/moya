template = """
@WRAPTEXT /media/readme.txt
Put any shared media (css, JS etc) here
@TEXT /__init__.py
# Required if you want to distribute your library as a Python module
@TEXT /lib.ini
[author]
name = ${{ author.name }}
email = ${{ author.email }}
organization = ${{ author.organization }}
url = ${{ author.url }}

[lib]
location = ./logic
title = ${{ library.title }}
url = ${{ library.url }}
namespace = ${{ library.namespace }}
name = ${{ library.longname }}
# Set to 0.1.0 for your first release
version = 0.1.0-dev

[settings]

[templates]
location = ./templates

[media:media]
location = ./media

[locale]
location = ./locale
default_language = en
languages = en

[documentation]
location = ./docs

[package]
exclude = __*__/*
    .*
    *.pyc
    .svn
    .hg
    .git

@WRAPTEXT /locale/readme.txt
Translations go here. Use the 'moya extract' command to create message catalogs.


@WRAPTEXT /templates/${{ library.longname }}/widgets/readme.txt
This folder should contain templates for widgets defined in the library.
@TEXT /templates/${{ library.longname }}/base.html
{% extends "/base.html" %}

{% block "body" %}
<h2>${{ library.title }}</h2>
<div class="alert alert-info">
    Created by <tt>moya start library</tt>
</div>
{% render sections.body %}

{% endblock %}
@TEXT /logic/content.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let"
      xmlns:db="http://moyaproject.com/db"
      xmlns:forms="http://moyaproject.com/forms"
      xmlns:html="http://moyaproject.com/html">

    <!-- Content is a high level description of a page -->
    <content libname="content.front" template="base.html">
        <section name="body">
            <html:div class="well" if="name">Hello, ${name}!</html:div>
            <render src="form" />
        </section>
    </content>

</moya>
@TEXT /logic/models.xml
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
@TEXT /logic/views.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let"
      xmlns:db="http://moyaproject.com/db"
      xmlns:forms="http://moyaproject.com/forms">

    <!-- Example view that gets a form -->
    <view libname="view.front" content="#content.front">
        <!-- Get the form -->
        <forms:get form="#form.getname" dst="form"/>
        <!-- Validate the form using POST data -->
        <forms:validate src="form" if=".request.POST">
            <!-- if the form validates set the value 'name' which is passed to the content -->
            <let name="form.data.name" />
        </forms:validate>
    </view>

</moya>
@TEXT /logic/signals.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
    xmlns:let="http://moyaproject.com/let"
    xmlns:db="http://moyaproject.com/db">

    <!-- define signals here -->
    <!--
    <handle signal="moya.auth.post-login">
        <echo>${signal.data.user} just logged in</echo>
    </handle>
    -->

</moya>
@TEXT /logic/forms.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com">

    <!-- Forms know how to render and validate themselves -->
    <form libname="form.getname" legend="Hello World Form" style="horizontal" xmlns="http://moyaproject.com/forms">
        <input name="name" label="What is your name?" class="input-xlarge" type="text" maxlength="30" required="yes"/>
        <submit-button text="Submit" />
    </form>

</moya>
@WRAPTEXT /logic/readme.txt
Moya code goes here

The filenames used here are just a suggestion of how to organize your Moya code -- all files with the extension .xml will be read.
@TEXT /logic/mountpoints.xml
<moya xmlns="http://moyaproject.com">

    <!-- Libraries will typically define a mountpoint to add URLs -->
    <mountpoint name="main">
        <!-- A simple default view to start you off -->
        <url route="/" methods="GET,POST" view="#view.front" name="front" />
    </mountpoint>

</moya>
@TEXT /logic/widgets.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let">
    <!-- define your widgets here -->


</moya>
@TEXT /logic/tags.xml
<?xml version="1.0" encoding="UTF-8"?>
<moya xmlns="http://moyaproject.com"
      xmlns:let="http://moyaproject.com/let">
    <!-- define your tags here -->

</moya>
"""
