from __future__ import unicode_literals
from __future__ import print_function

from moya.template import Template
from moya.context import Context

simple = """
{%- for n in 1..3 %}
hello ${name}, ${n}
{%- endfor %}
"""

if __name__ == "__main__":

    context = Context({'name': 'World'})
    t = Template(simple)
    t.parse()
    result = t.render(context)
    print(result)
