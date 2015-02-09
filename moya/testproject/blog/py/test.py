from __future__ import print_function

import moya

@moya.expose.macro("test")
def test():
    print("Success! :-)")
    return 10