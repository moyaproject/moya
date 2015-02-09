from __future__ import unicode_literals

css = """

body
{
    background-color:#222;
    color:#fff;
    line-height:1em
}

pre.moya-console {
    font-family:monospace;
    font-size:12px;
    line-height:1.3em;
}

.moya-console .console-bold
{
    font-weight: bold;
}

.moya-console .console-italic
{
    font-style: italic;
}

.moya-console .console-underline
{
    text-decoration: underline;
}

.moya-console .console-dim
{
    opacity:.5;
    font-weight:normal !important;
}


.moya-console .console-bold.console-foreground-yellow
{
    color: #fce94f;
}

.moya-console .console-bold.console-foreground-magenta
{
    color: #ad7fa8;
}

.moya-console .console-bold.console-foreground-green
{
    color: #8ae234;
}

.moya-console .console-bold.console-foreground-blue
{
    color: #729fcf;
}

.moya-console .console-bold.console-foreground-cyan
{
    color: #34e2e2
}

.moya-console .console-bold.console-foreground-red
{
    color: #ef2929;
}

.moya-console .console-bold.console-foreground-black
{
    color: #555753
}

.moya-console .console-bold.console-foreground-white
{
    color: #eeeeec
}


.moya-console .console-foreground-yellow
{
    color: #c4a000;
}

.moya-console .console-foreground-magenta
{
    color: #75507b;
}

.moya-console .console-foreground-green
{
    color: #4e9a06;
}

.moya-console .console-foreground-blue
{
    color: #3465a4;
}

.moya-console .console-foreground-cyan
{
    color: #06989a
}

.moya-console .console-foreground-red
{
    color: #cc0000;
}

.moya-console .console-foreground-black
{
    color: #000000
}

.moya-console .console-foreground-white
{
    color: #d3d7cf
}



.moya-console .console-background-yellow
{
    background-color: #fce94f;
}

.moya-console .console-background-magenta
{
    background-color: #ad7fa8;
}

.moya-console .console-background-green
{
    background-color: #8ae234;
}

.moya-console .console-background-blue
{
    background-color: #729fcf;
}

.moya-console .console-background-cyan
{
    background-color: #34e2e2
}

.moya-console .console-background-red
{
    background-color: #ef2929;
}

.moya-console .console-background-black
{
    background-color: #555753
}

.moya-console .console-background-white
{
    background-color: #eeeeec
}


"""

_template = """
<!doctype html>
<head>
<meta charset="UTF-8">
<style>
{css}
</style>
</head>
<body>
<pre class="moya-console">
{html}
</pre>
</body>
"""


def render_console_html(html):
    """Render html from the console in to a page of HTML"""
    return _template.format(html=html, css=css)
