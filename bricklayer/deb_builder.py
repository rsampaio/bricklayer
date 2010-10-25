import os
import sys
import shutil
import time
import re
import glob
import stat
import logging as log
import subprocess

from projects import Projects
from config import BrickConfig

from git import Git

class DebBuilder():
    def __init__(self, builder):
        self.builder = builder
        self.project = self.builder.project

    def build(self, branch, last_tag=None):
        templates = {}
        templates_dir = os.path.join(self.builder.templates_dir, 'deb')
        debian_dir = os.path.join(self.builder.workdir, 'debian')
        control_data_original = None
        control_data_new = None

        if self.project.install_prefix is None:
            self.project.install_prefix = 'opt'

        if not self.project.install_cmd :

            self.project.install_cmd = 'cp -r \`ls | grep -v debian\` debian/tmp/%s' % (
                    self.project.install_prefix
                )

        template_data = {
                'name': self.project.name,
                'version': "%s" % (self.project.version(branch)),
                'build_cmd': self.project.build_cmd,
                'install_cmd': self.builder.mod_install_cmd,
                'username': self.project.username,
                'email': self.project.email,
                'date': time.strftime("%a, %d %h %Y %T %z"),
            }

        def read_file_data(f):
            template_fd = open(os.path.join(templates_dir, f))
            templates[f] = pystache.template.Template(template_fd.read()).render(context=template_data)
            template_fd.close()

        if not os.path.isdir(debian_dir):

            map(read_file_data, ['changelog', 'control', 'rules'])
            
            os.makedirs( os.path.join( debian_dir, self.project.name, self.project.install_prefix))

            for filename, data in templates.iteritems():
                open(os.path.join(debian_dir, filename), 'w').write(data)
        
        changelog_entry = """%(name)s (%(version)s) %(branch)s; urgency=low

  * Latest commits
  %(commits)s

 -- %(username)s <%(email)s>  %(date)s
"""
        changelog_data = {
                'name': self.project.name,
                'version': self.project.version(branch),
                'branch': branch,
                'commits': '  '.join(self.builder.git.log()),
                'username': self.project.username,
                'email': self.project.email,
                'date': time.strftime("%a, %d %h %Y %T %z"),
            }


        if last_tag != None and last_tag.startswith('stable'):
            self.project.version('stable', last_tag.split('_')[1])
            changelog_data.update({'version': self.project.version('stable'), 'branch': 'stable'})

        elif last_tag != None and last_tag.startswith('testing'):
            self.project.version('testing', last_tag.split('_')[1])
            changelog_data.update({'version': self.project.version('testing'), 'branch': 'testing'})

        else:
            """
            otherwise it should change the package name to something that can differ from the stable version
            like appending -branch to the package name by changing its control file
            """
            control = os.path.join(self.builder.workdir, 'debian', 'control')
            if os.path.isfile(control):
                control_data_original = open(control).read()
                control_data_new = control_data_original.replace(self.project.name, "%s-%s" % (self.project.name, branch))
                open(control, 'w').write(control_data_new)
            
            if self.project.version(branch):
                version_list = self.project.version(branch).split('.')
                version_list[len(version_list) - 1] = str(int(version_list[len(version_list) - 1]) + 1)
                self.project.version(branch, '.'.join(version_list))

            changelog_data.update({'version': self.project.version(branch), 'name': "%s-%s" % (self.project.name, branch), 'branch': 'testing'})

        open(os.path.join(self.builder.workdir, 'debian', 'changelog'), 'w').write(changelog_entry % changelog_data)
        
        self.project.version(branch, open(os.path.join(self.builder.workdir, 'debian/changelog'), 'r').readline().split('(')[1].split(')')[0])
        self.project.save()
            
        rvm_env = {}
        rvm_rc = os.path.join(self.builder.workdir, '.rvmrc')
        rvm_rc_example = rvm_rc +  ".example"
        has_rvm = False

        if os.path.isfile(rvm_rc):
            has_rvm = True
        elif os.path.isfile(rvm_rc_example):
            has_rvm = True
            rvm_rc = rvm_rc_example
        
        if has_rvm:
            rvmexec = open(rvm_rc).read()
            log.info("RVMRC: %s" % rvmexec)
            
            # I need the output not to log on file
            rvm_cmd = subprocess.Popen('/usr/local/bin/rvm info %s' % rvmexec.split()[1],
                    shell=True, stdout=subprocess.PIPE)
            rvm_cmd.wait()
            for line in rvm_cmd.stdout.readlines():
                if 'PATH' in line or 'HOME' in line:
                    name, value = line.split()
                    rvm_env[name.strip(':')] = value.strip('"')
            rvm_env['HOME'] = os.environ['HOME']
            log.info(rvm_env)

        if len(rvm_env.keys()) < 1:
            rvm_env = os.environ
        else:
            try:
                os.environ.pop('GEM_HOME')
                os.environ.pop('BUNDLER_PATH')
            except Exception, e:
                pass
            rvm_env.update(os.environ)

        os.chmod(os.path.join(debian_dir, 'rules'), stat.S_IRWXU|stat.S_IRWXG|stat.S_IROTH|stat.S_IXOTH)
        dpkg_cmd = self.builder._exec(
                ['dpkg-buildpackage',  '-rfakeroot', '-k%s' % BrickConfig().get('gpg', 'keyid')],
                cwd=self.builder.workdir, env=rvm_env
        )
        
        dpkg_cmd.wait()
        
        control = os.path.join(self.builder.workdir, 'debian', 'control')
        if os.path.isfile(control) and control_data_original:
            open(control, 'w').write(control_data_original)

        clean_cmd = self.builder._exec(['dh', 'clean'], cwd=self.builder.workdir)
        clean_cmd.wait()

    def upload(self, branch):
        if branch == 'stable':
            print '%s/%s_%s_*.changes' % (self.builder.workspace, self.project.name, self.project.version(branch))
            changes_file = glob.glob('%s/%s_%s_*.changes' % (self.builder.workspace, self.project.name, self.project.version(branch)))[0]
            upload_cmd = self.builder._exec(['dput', branch, changes_file])
        else:
            print '%s/%s-%s_%s_*.changes' % (self.builder.workspace, self.project.name, branch, self.project.version(branch))
            changes_file = glob.glob('%s/%s-%s_%s_*.changes' % (self.builder.workspace, self.project.name, branch, self.project.version(branch)))[0]
            upload_cmd = self.builder._exec(['dput',  changes_file])
        upload_cmd.wait()

    def promote_to(self, version, release):
        self.project.version(version=version)
        self.project.release = release
        self.project.save()

    def promote_deb(self):
        self.builder.git.create_tag("%s.%s" % (self.project.version(), self.project.release))
        dch_cmd = self.builder._exec(['dch', '-r', '--no-force-save-on-release', '--newversion', '%s.%s' % (self.project.version(), self.project.release)], cwd=self.builder.workdir)
        dch_cmd.wait()

