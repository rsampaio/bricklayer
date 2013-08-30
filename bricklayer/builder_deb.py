import os
import sys
import shutil
import time
import re
import glob
import stat
import subprocess
import ftplib
import pystache
import logging
from urlparse import urlparse

from projects import Projects
from config import BrickConfig
from build_info import BuildInfo

log = logging.getLogger('builder')

class BuilderDeb():
    def __init__(self, builder):
        self.builder = builder
        self.project = self.builder.project
        log.info("Debian builder initialized: %s" % self.builder.workdir)
        log.info("Building [%s] with options: %s" % (
                self.project.name, 
                self.builder.build_options.options
                ))
    
    def configure_changelog(self, branch):
        template_data = {
                'name': self.project.name,
                'version': "%s" % (self.project.version(branch)),
                'build_cmd': self.project.build_cmd,
                'install_cmd': self.builder.mod_install_cmd,
                'username': self.project.username,
                'email': self.project.email,
                'date': time.strftime("%a, %d %h %Y %T %z"),
            }

        changelog = os.path.join(self.builder.workdir, 'debian', 'changelog')
        
        if hasattr(self.builder.build_options, 'changelog') and self.builder.build_options.changelog:
            if os.path.isfile(changelog):
                os.rename(changelog, "%s.save" % changelog)

            def read_file_data(f):
                with open(os.path.join(templates_dir, f)) as tmpfh:
                    templates[f] = pystache.template.Template(tmpfh.read()).render(context=template_data)

            if not os.path.isdir(self.debian_dir):

                map(read_file_data, ['changelog', 'control', 'rules'])

                os.makedirs( os.path.join(self.debian_dir, self.project.name, self.project.install_prefix))

                for filename, data in templates.iteritems():
                    with open(os.path.join(self.debian_dir, filename), 'w') as tmpfh:
                        tmpfh.write(data)

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
            return (changelog_entry, changelog_data)

        else:
            return (None, None)

    def build_install_deps(self):
        p = self.builder._exec(["dpkg-checkbuilddeps"], stderr=subprocess.PIPE, close_fds=True)
        p.wait()
        out = p.stderr.read()
        if out != "":
            deps = re.findall("([a-z0-9\-]+\s|[a-z0-9\-]+$)", out.split("dependencies:")[1])
            deps = map(lambda x: x.strip(), deps)
            apt_cmd = "apt-get -y --force-yes install %s" % " ".join(deps)
            b = self.builder._exec(apt_cmd.split(), stdout=self.stdout, stderr=self.stderr, close_fds=True)
            b.wait()
            

    def build(self, branch, last_tag=None, force_version=None, force_release=None):
        templates = {}
        templates_dir = os.path.join(self.builder.templates_dir, 'deb')
        control_data_new = None

        self.build_info = BuildInfo(self.project.name)
        logfile = os.path.join(
                BrickConfig().get("workspace", "dir"), 'log', '%s.%s.log' % (
                    self.project.name, self.build_info.build_id
                    )
                )
        log.info("build log file: %s" % logfile)
        self.build_info.log(logfile)
        self.stdout = open(logfile, 'a+')
        self.stderr = self.stdout
        self.debian_dir = os.path.join(self.builder.workdir, 'debian')
        
        if last_tag is not None:
            os.environ.update({'BRICKLAYER_RELEASE': last_tag.split('_')[0]})
            os.environ.update({'BRICKLAYER_TAG': last_tag})

        # Not now
        #self.build_install_deps()

        if self.project.install_prefix is None:
            self.project.install_prefix = 'opt'

        if not self.project.install_cmd :
            self.project.install_cmd = 'cp -r \`ls | grep -v debian\` debian/tmp/%s' % (
                self.project.install_prefix
            )

        changelog_entry, changelog_data = self.configure_changelog(branch)

        if changelog_entry and changelog_data:
            if last_tag != None and last_tag.startswith('stable'):
                self.project.version('stable', last_tag.split('_')[1])
                changelog_data.update({'version': self.project.version('stable'), 'branch': 'stable'})
                self.build_info.version(self.project.version('stable'))
                self.build_info.release('stable')

            elif last_tag != None and last_tag.startswith('testing'):
                self.project.version('testing', last_tag.split('_')[1])
                changelog_data.update({'version': self.project.version('testing'), 'branch': 'testing'})
                self.build_info.version(self.project.version('testing'))
                self.build_info.release('testing')

            elif last_tag != None and last_tag.startswith('unstable'):
                self.project.version('unstable', last_tag.split('_')[1])
                changelog_data.update({'version': self.project.version('unstable'), 'branch': 'unstable'})
                self.build_info.version(self.project.version('unstable'))
                self.build_info.release('unstable')

            else:
                """
                otherwise it should change the distribution to experimental
                """
                version_list = self.project.version(branch).split('.')
                version_list[len(version_list) - 1] = str(int(version_list[len(version_list) - 1]) + 1)
                self.project.version(branch, '.'.join(version_list))
                
                changelog_data.update({'version': self.project.version(branch), 'branch': 'experimental'})
                self.build_info.version(self.project.version(branch))
                self.build_info.release('experimental:%s' % branch)
            
            with file(os.path.join(self.builder.workdir, 'debian', 'changelog'), 'w') as fh:
                fh.write(changelog_entry % changelog_data)

        else:
            self.build_info.version(force_version)
            self.build_info.release(force_release)
            self.project.version(branch, force_version)
            self.project.version(force_release, force_version)

        

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
            with open(rvm_rc) as tmpfh:
                rvmexec = tmpfh.read()
            log.info("RVMRC: %s" % rvmexec)

            # I need the output not to log on file
            rvm_cmd = subprocess.Popen('/usr/local/rvm/bin/rvm info %s' % rvmexec.split()[1],
                    shell=True, stdout=subprocess.PIPE)
            rvm_cmd.wait()
            for line in rvm_cmd.stdout.readlines():
                if 'PATH' in line or 'HOME' in line:
                    name, value = line.split()
                    rvm_env[name.strip(':')] = value.strip('"')
            rvm_env['HOME'] = os.environ['HOME']

        if len(rvm_env.keys()) < 1:
            rvm_env = os.environ
        else:
            os_env = dict(os.environ)
            for k in ("PATH", "GEM_HOME", "BUNDLER_PATH"):
                if (k in os_env):
                    del(os_env[k])
            rvm_env.update(os_env)

	log.info(rvm_env)

        os.chmod(os.path.join(self.debian_dir, 'rules'), stat.S_IRWXU|stat.S_IRWXG|stat.S_IROTH|stat.S_IXOTH)
        dpkg_cmd = self.builder._exec(
                ['dpkg-buildpackage',  
                 '-rfakeroot', '-tc', '-k%s' % BrickConfig().get('gpg', 'keyid')],
                cwd=self.builder.workdir, env=rvm_env, stdout=self.stdout, stderr=self.stderr, close_fds=True)
        dpkg_cmd.wait()

        clean_cmd = self.builder._exec(['dh', 'clean'], 
                                       cwd=self.builder.workdir, 
                                       stdout=self.stdout, stderr=self.stderr, close_fds=True)
        clean_cmd.wait()


    def upload(self, branch):
        glob_str = '%s/%s_%s_*.changes' % (
                BrickConfig().get('workspace', 'dir'), 
                self.project.name, self.project.version(branch))
        changes_file = glob.glob(glob_str)
	log.info(changes_file)
        distribution, files = self.parse_changes(changes_file[0])

        try:
            self.upload_files(distribution, files)
            upload_file = changes_file[0].replace('.changes', '.upload')
            with open(upload_file, 'w') as tmpfh:
                tmpfh.write("done")
        except Exception, e:
            log.error("Package could not be uploaded: %s", e)

    def parse_changes(self, changes_file):
        with open(changes_file) as tmpfh:
            content = tmpfh.readlines()
        go = 0
        distribution = ""
        tmpfiles = [os.path.basename(changes_file)]
        for line in content:
            if line.startswith('Distribution'):
                distribution = line.strip('\n')
                distribution = distribution.split(':')[1].strip(' ')
            if line.startswith('File'):
                go = 1
            elif not line.startswith('\n') and go == 1:
                tmpname = line.split()
                pos = len(tmpname)
                tmpfiles.append(tmpname[pos-1])
            else:
                go = 0
        files = []
        for f in tmpfiles:
            filename = f.split()
            files.append(filename[len(filename) - 1])
	log.info(">>>>>")
	log.info(files)
        return distribution, files

    def local_repo(self, distribution, files):
        archive_conf_data = """Dir {
  ArchiveDir "%s/%s";
};

BinDirectory "dists/unstable" {
  Packages "dists/unstable/main/binary-amd64/Packages";
  SrcPackages "dists/unstable/main/source/Sources";
};

BinDirectory "dists/stable" {
  Packages "dists/stable/main/binary-amd64/Packages";
  SrcPackages "dists/stable/main/source/Sources";
};

BinDirectory "dists/testing" {
  Packages "dists/testing/main/binary-amd64/Packages";
  SrcPackages "dists/testing/main/source/Sources";
};

BinDirectory "dists/experimental" {
  Packages "dists/experimental/main/binary-amd64/Packages";
  SrcPackages "dists/experimental/main/source/Sources";
};"""
        repo_bin_path = os.path.join(BrickConfig().get("local_repo", "dir"), 
                self.project.group_name, 'dists/%s/main/binary-amd64/' % distribution)
        repo_src_path = os.path.join(BrickConfig().get("local_repo", "dir"), 
                self.project.group_name, 'dists/%s/main/source/' % distribution)

        archive_conf_file = os.path.join(
                BrickConfig().get("local_repo", "dir"), 
                self.project.group_name, 
                'archive.conf')

        if not os.path.isdir(repo_bin_path) or not os.path.isdir(repo_src_path):
            os.makedirs(repo_bin_path)
            os.makedirs(repo_src_path)

            if not os.path.isfile(archive_conf_file):
                with open(archive_conf_file, 'w') as tmpfh:
                    tmpfh.write(
                        archive_conf_data % (
                            BrickConfig().get("local_repo", "dir"), 
                            self.project.group_name
                        ))
        
        workspace = BrickConfig().get("workspace", "dir")
        for f in files:
            f = f.strip()
            if f.endswith('.dsc') or f.endswith('.tar.gz'):
                shutil.copy(os.path.join(workspace, f), os.path.join(repo_src_path, f))
            elif f.endswith('.deb'):
                shutil.copy(os.path.join(workspace, f), os.path.join(repo_bin_path, f))

        repo_base_path = os.path.join(BrickConfig().get('local_repo', 'dir'), self.project.group_name)
        

    def upload_files(self, distribution, files):
        repository_url, user, passwd = self.project.repository()
        if not repository_url:
            return 0
        # os.chdir(BrickConfig().get('workspace', 'dir'))
        workspace = BrickConfig().get('workspace', 'dir')
        ftp = ftplib.FTP(repository_url, user, passwd)
        try:
            ftp.cwd(distribution)
            for f in files:
                log.info("\t%s: " % os.path.join(workspace, f))
                with open(os.path.join(workspace, f), 'rb') as tmpfh:
                    ftp.storbinary("STOR %s" % f, tmpfh)
                log.info("done.")
        except Exception, e:
            log.info(repr(e))
        ftp.quit()
