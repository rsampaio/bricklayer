import os
from distutils.core import setup
try:
    import twisted
except ImportError:
    raise SystemExit("twisted not found.  Make sure you "
                     "have installed the Twisted core package.")
def refresh_plugin_cache():
    from twisted.plugin import IPlugin, getPlugins
    list(getPlugins(IPlugin))

template_dir = []
for root, dirs, files in os.walk('pkg_template'):
    if not dirs: 
        template_dir.append((os.path.join('/var/lib/bricklayer/', root), 
            map(lambda x: os.path.join(root, x), files))
        )

        
for root, dirs, files in os.walk('web'):
    if not dirs: 
        template_dir.append((os.path.join('/var/lib/bricklayer/', root), 
            map(lambda x: os.path.join(root, x), files))
        )
    else:
        template_dir.append((os.path.join('/var/lib/bricklayer/', root), 
            map(lambda x: os.path.join(root, x), files))
        )


data_files_list = template_dir
data_files_list.extend([
        ('/etc/bricklayer/', [
                'etc/bricklayer/bricklayer.ini',
                'etc/bricklayer/gpg.key']),
        ])
data_files_list.append(("/usr/bin", ["bin/bricklayer-rvm-exec"]))

setup(
    name='bricklayer',
    version='1.0',
    author = "Rodrigo Sampaio Vaz",
    author_email = "rodrigo.vaz@gmail.com",
    description = ("A package builder that watch git repositories"
                                   "developed at locaweb."),
    license='Apache License',
    keywords = "package builder debian rpm",
    url = "http://locaweb.github.com",
    packages= [ "bricklayer", "bricklayer.utils.pystache", "twisted.plugins" ],
    package_data = { "twisted" : [
            "plugins/txbricklayer.py", 
            "plugins/txbricklayer_web.py"] },
    include_package_data = True,
    data_files=data_files_list
)

refresh_plugin_cache()
