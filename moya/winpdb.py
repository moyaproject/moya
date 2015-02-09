import os


def breakpoint():
    import rpdb2
    os.system('winpdb -r &')
    rpdb2.start_embedded_debugger("password")
