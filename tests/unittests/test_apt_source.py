# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_apt_source
Testing various config variations of the apt_source custom config
"""
import glob
import os
import re
import socket


import mock
from mock import call

from aptsources.sourceslist import SourceEntry

from curtin import distro
from curtin import gpg
from curtin import util
from curtin.commands import apt_config
from .helpers import CiTestCase


EXPECTEDKEY = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1

mI0ESuZLUgEEAKkqq3idtFP7g9hzOu1a8+v8ImawQN4TrvlygfScMU1TIS1eC7UQ
NUA8Qqgr9iUaGnejb0VciqftLrU9D6WYHSKz+EITefgdyJ6SoQxjoJdsCpJ7o9Jy
8PQnpRttiFm4qHu6BVnKnBNxw/z3ST9YMqW5kbMQpfxbGe+obRox59NpABEBAAG0
HUxhdW5jaHBhZCBQUEEgZm9yIFNjb3R0IE1vc2VyiLYEEwECACAFAkrmS1ICGwMG
CwkIBwMCBBUCCAMEFgIDAQIeAQIXgAAKCRAGILvPA2g/d3aEA/9tVjc10HOZwV29
OatVuTeERjjrIbxflO586GLA8cp0C9RQCwgod/R+cKYdQcHjbqVcP0HqxveLg0RZ
FJpWLmWKamwkABErwQLGlM/Hwhjfade8VvEQutH5/0JgKHmzRsoqfR+LMO6OS+Sm
S0ORP6HXET3+jC8BMG4tBWCTK/XEZw==
=ACB2
-----END PGP PUBLIC KEY BLOCK-----"""

ADD_APT_REPO_MATCH = r"^[\w-]+:\w"

TARGET = "/"


def load_tfile(filename):
    """ load_tfile
    load file and return content after decoding
    """
    try:
        content = util.load_file(filename, decode=True)
    except Exception as error:
        print('failed to load file content for test: %s' % error)
        raise

    return content


class PseudoChrootableTarget(util.ChrootableTarget):
    # no-ops the mounting and modifying that ChrootableTarget does
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return


ChrootableTargetStr = "curtin.commands.apt_config.util.ChrootableTarget"


def entryify(data):
    return [SourceEntry(line) for line in data.splitlines()]


def lineify(entries):
    out = apt_config.entries_to_str(entries)
    # the tests are written without the trailing newline,
    # but we don't want to remove multiple of them
    out = out[:-1] if len(out) > 0 and out[-1] == '\n' else out
    return out


class TestAptSourceConfig(CiTestCase):
    """ TestAptSourceConfig
    Main Class to test apt configs
    """
    def setUp(self):
        super(TestAptSourceConfig, self).setUp()
        self.tmp = self.tmp_dir()
        self.aptlistfile = os.path.join(self.tmp, "single-deb.list")
        self.aptlistfile2 = os.path.join(self.tmp, "single-deb2.list")
        self.aptlistfile3 = os.path.join(self.tmp, "single-deb3.list")
        self.join = os.path.join
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search
        self.add_patch('curtin.util.subp', 'm_subp')
        self.m_subp.return_value = ('s390x', '')
        self.target = self.tmp_dir()

    @staticmethod
    def _add_apt_sources(*args, **kwargs):
        with mock.patch.object(distro, 'apt_update'):
            apt_config.add_apt_sources(*args, **kwargs)

    @staticmethod
    def _get_default_params():
        """ get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = distro.lsb_release()['codename']
        arch = distro.get_architecture()
        params['MIRROR'] = apt_config.get_default_mirrors(arch)["PRIMARY"]
        return params

    def _myjoin(self, *args, **kwargs):
        """ _myjoin - redir into writable tmpdir"""
        if (args[0] == "/etc/apt/sources.list.d/" and
                args[1] == "cloud_config_sources.list" and
                len(args) == 2):
            return self.join(self.tmp, args[0].lstrip("/"), args[1])
        else:
            return self.join(*args, **kwargs)

    def _apt_src_basic(self, filename, cfg):
        """ _apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        self._add_apt_sources(cfg, TARGET, template_params=params,
                              aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic(self):
        """test_apt_src_basic - Test fix deb source string"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

    def test_apt_src_basic_tri(self):
        """test_apt_src_basic_tri - Test multiple fix deb source strings"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')},
               self.aptlistfile2: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' precise-backports'
                                    ' main universe multiverse restricted')},
               self.aptlistfile3: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' lucid-backports'
                                    ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def _apt_src_replacement(self, filename, cfg):
        """ apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        self._add_apt_sources(cfg, TARGET, template_params=params,
                              aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace(self):
        """test_apt_src_replace - Test Autoreplacement of MIRROR and RELEASE"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'}}
        self._apt_src_replacement(self.aptlistfile, cfg)

    def test_apt_src_replace_fn(self):
        """test_apt_src_replace_fn - Test filename being overwritten in dict"""
        cfg = {'ignored': {'source': 'deb $MIRROR $RELEASE multiverse',
                           'filename': self.aptlistfile}}
        # second file should overwrite the dict key
        self._apt_src_replacement(self.aptlistfile, cfg)

    def _apt_src_replace_tri(self, cfg):
        """ _apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self._apt_src_replacement(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        params = self._get_default_params()
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "main"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "universe"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace_tri(self):
        """test_apt_src_replace_tri - Test multiple replacements/overwrites"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused':        {'source': 'deb $MIRROR $RELEASE main',
                                  'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self._apt_src_replace_tri(cfg)

    def _apt_src_keyid(self, filename, cfg, keynum):
        """ _apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch("curtin.util.subp",
                        return_value=('fakekey 1234', '')) as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        # check if it added the right ammount of keys
        calls = []
        for _ in range(keynum):
            calls.append(call(['apt-key', 'add', '-'], data=b'fakekey 1234',
                              target=TARGET))
        mockobj.assert_has_calls(calls, any_order=True)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyid(self):
        """test_apt_src_keyid - Test source + keyid with filename being set"""
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"}}
        self._apt_src_keyid(self.aptlistfile, cfg, 1)

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyid_tri(self):
        """test_apt_src_keyid_tri - Test multiple src+keyid+filen overwrites"""
        cfg = {self.aptlistfile:  {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial main'),
                                   'keyid': "03683F77"},
               'ignored':         {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial universe'),
                                   'keyid': "03683F77",
                                   'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial multiverse'),
                                   'keyid': "03683F77"}}

        self._apt_src_keyid(self.aptlistfile, cfg, 3)
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "universe"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "multiverse"),
                                  contents, flags=re.IGNORECASE))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_key(self):
        """test_apt_src_key - Test source + key"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'key': "fakekey 4321"}}

        with mock.patch.object(util, 'subp') as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 4321',
                                target=TARGET)

        self.assertTrue(os.path.isfile(self.aptlistfile))

        contents = load_tfile(self.aptlistfile)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyonly(self):
        """test_apt_src_keyonly - Test key without source"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'key': "fakekey 4242"}}

        with mock.patch.object(util, 'subp') as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 4242',
                                target=TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyidonly(self):
        """test_apt_src_keyidonly - Test keyid without source"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': "03683F77"}}

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)

        mockobj.assert_any_call(['apt-key', 'add', '-'], data=b'fakekey 1212',
                                target=TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def apt_src_keyid_real(self, cfg, expectedkey):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        params = self._get_default_params()

        with mock.patch.object(apt_config, 'add_apt_key_raw') as mockkey:
            with mock.patch.object(gpg, 'getkeybyid',
                                   return_value=expectedkey) as mockgetkey:
                self._add_apt_sources(cfg, TARGET, template_params=params,
                                      aa_repo_match=self.matcher)

        keycfg = cfg[self.aptlistfile]
        mockgetkey.assert_called_with(keycfg['keyid'],
                                      keycfg.get('keyserver',
                                                 'keyserver.ubuntu.com'),
                                      retries=(1, 2, 5, 10))
        mockkey.assert_called_with(expectedkey, TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyid_real(self):
        """test_apt_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_longkeyid_real(self):
        """test_apt_src_longkeyid_real Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_longkeyid_ks_real(self):
        """test_apt_src_longkeyid_ks_real Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'keys.gnupg.net'}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    def test_apt_src_keyid_keyserver(self):
        """test_apt_src_keyid_keyserver - Test custom keyserver"""
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'test.random.com'}}

        # in some test environments only *.ubuntu.com is reachable
        # so mock the call and check if the config got there
        with mock.patch.object(gpg, 'getkeybyid',
                               return_value="fakekey") as mockgetkey:
            with mock.patch.object(apt_config, 'add_apt_key_raw') as mockadd:
                self._add_apt_sources(cfg, TARGET, template_params=params,
                                      aa_repo_match=self.matcher)

        mockgetkey.assert_called_with('03683F77', 'test.random.com',
                                      retries=(1, 2, 5, 10))
        mockadd.assert_called_with('fakekey', TARGET)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_ppa(self):
        """test_apt_src_ppa - Test specification of a ppa"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'}}

        with mock.patch("curtin.util.subp") as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)
        mockobj.assert_any_call(['add-apt-repository',
                                 'ppa:smoser/cloud-init-test'],
                                retries=(1, 2, 5, 10), target=TARGET)

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))

    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_ppa_tri(self):
        """test_apt_src_ppa_tri - Test specification of multiple ppa's"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'},
               self.aptlistfile2: {'source': 'ppa:smoser/cloud-init-test2'},
               self.aptlistfile3: {'source': 'ppa:smoser/cloud-init-test3'}}

        with mock.patch("curtin.util.subp") as mockobj:
            self._add_apt_sources(cfg, TARGET, template_params=params,
                                  aa_repo_match=self.matcher)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test'],
                      retries=(1, 2, 5, 10), target=TARGET),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2'],
                      retries=(1, 2, 5, 10), target=TARGET),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'],
                      retries=(1, 2, 5, 10), target=TARGET)]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))
        self.assertFalse(os.path.isfile(self.aptlistfile2))
        self.assertFalse(os.path.isfile(self.aptlistfile3))

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_mir_apt_list_rename(self, m_get_architecture):
        """test_mir_apt_list_rename - Test find mirror and apt list renaming"""
        pre = "/var/lib/apt/lists"
        # filenames are archive dependent

        arch = 's390x'
        m_get_architecture.return_value = arch
        component = "ubuntu-ports"
        archive = "ports.ubuntu.com"

        cfg = {'primary': [{'arches': ["default"],
                            'uri':
                            'http://test.ubuntu.com/%s/' % component}],
               'security': [{'arches': ["default"],
                             'uri':
                             'http://testsec.ubuntu.com/%s/' % component}]}
        post = ("%s_dists_%s-updates_InRelease" %
                (component, distro.lsb_release()['codename']))
        fromfn = ("%s/%s_%s" % (pre, archive, post))
        tofn = ("%s/test.ubuntu.com_%s" % (pre, post))

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['MIRROR'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['PRIMARY'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['SECURITY'],
                         "http://testsec.ubuntu.com/%s/" % component)

        with mock.patch.object(os, 'rename') as mockren:
            with mock.patch.object(glob, 'glob',
                                   return_value=[fromfn]):
                apt_config.rename_apt_lists(mirrors, TARGET)

        mockren.assert_any_call(fromfn, tofn)

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_mir_apt_list_rename_non_slash(self, m_get_architecture):
        target = os.path.join(self.tmp, "rename_non_slash")
        apt_lists_d = os.path.join(target, "./" + apt_config.APT_LISTS)

        m_get_architecture.return_value = 'amd64'

        mirror_path = "some/random/path/"
        primary = "http://test.ubuntu.com/" + mirror_path
        security = "http://test-security.ubuntu.com/" + mirror_path
        mirrors = {'PRIMARY': primary, 'SECURITY': security}

        # these match default archive prefixes
        opri_pre = "archive.ubuntu.com_ubuntu_dists_xenial"
        osec_pre = "security.ubuntu.com_ubuntu_dists_xenial"
        # this one won't match and should not be renamed defaults.
        other_pre = "dl.google.com_linux_chrome_deb_dists_stable"
        # these are our new expected prefixes
        npri_pre = "test.ubuntu.com_some_random_path_dists_xenial"
        nsec_pre = "test-security.ubuntu.com_some_random_path_dists_xenial"

        files = [
            # orig prefix, new prefix, suffix
            (opri_pre, npri_pre, "_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "_main_binary-amd64_InRelease"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_InRelease"),
            (other_pre, other_pre, "_main_binary-amd64_Packages"),
            (other_pre, other_pre, "_Release"),
            (other_pre, other_pre, "_Release.gpg"),
            (osec_pre, nsec_pre, "_InRelease"),
            (osec_pre, nsec_pre, "_main_binary-amd64_Packages"),
            (osec_pre, nsec_pre, "_universe_binary-amd64_Packages"),
        ]

        expected = sorted([npre + suff for opre, npre, suff in files])
        # create files
        for (opre, npre, suff) in files:
            fpath = os.path.join(apt_lists_d, opre + suff)
            util.write_file(fpath, content=fpath)

        apt_config.rename_apt_lists(mirrors, target)
        found = sorted(os.listdir(apt_lists_d))
        self.assertEqual(expected, found)

    @staticmethod
    def test_apt_proxy():
        """test_apt_proxy - Test apt_*proxy configuration"""
        cfg = {"proxy": "foobar1",
               "http_proxy": "foobar2",
               "ftp_proxy": "foobar3",
               "https_proxy": "foobar4"}

        with mock.patch.object(util, 'write_file') as mockobj:
            apt_config.apply_apt_proxy_config(cfg, "proxyfn", "notused")

        mockobj.assert_called_with('proxyfn',
                                   ('Acquire::http::Proxy "foobar1";\n'
                                    'Acquire::http::Proxy "foobar2";\n'
                                    'Acquire::ftp::Proxy "foobar3";\n'
                                    'Acquire::https::Proxy "foobar4";\n'))

    def test_preference_to_str(self):
        """ test_preference_to_str - Test converting a preference dict to
        textual representation.
        """
        preference = {
            "package": "*",
            "pin": "release a=unstable",
            "pin-priority": 50,
        }

        expected = """\
Package: *
Pin: release a=unstable
Pin-Priority: 50
"""
        self.assertEqual(expected, apt_config.preference_to_str(preference))

    @staticmethod
    def test_apply_apt_preferences():
        """ test_apply_apt_preferences - Test apt preferences configuration
        """
        cfg = {
            "preferences": [
                {
                    "package": "*",
                    "pin": "release a=unstable",
                    "pin-priority": 50,
                }, {
                    "package": "dummy-unwanted-package",
                    "pin": "origin *ubuntu.com*",
                    "pin-priority": -1,
                }
            ]
        }

        expected_content = """\
Package: *
Pin: release a=unstable
Pin-Priority: 50

Package: dummy-unwanted-package
Pin: origin *ubuntu.com*
Pin-Priority: -1
"""
        with mock.patch.object(util, "write_file") as mockobj:
            apt_config.apply_apt_preferences(cfg, "preferencesfn")

        mockobj.assert_called_with("preferencesfn", expected_content)

    def test_mirror(self):
        """test_mirror - Test defining a mirror"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir}],
               "security": [{'arches': ["default"],
                             "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_default(self):
        """test_mirror_default - Test without defining a mirror"""
        arch = distro.get_architecture()
        default_mirrors = apt_config.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mirrors = apt_config.find_apt_mirror_info({}, arch)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_arches(self):
        """test_mirror_arches - Test arches selection of mirror"""
        pmir = "http://my-primary.ubuntu.com/ubuntu/"
        smir = "http://my-security.ubuntu.com/ubuntu/"
        arch = 'ppc64el'
        cfg = {"primary": [{'arches': ["default"], "uri": "notthis-primary"},
                           {'arches': [arch], "uri": pmir}],
               "security": [{'arches': ["default"], "uri": "nothis-security"},
                            {'arches': [arch], "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_mirror_arches_default(self):
        """test_mirror_arches - Test falling back to default arch"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthis"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["default"],
                             "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_get_default_mirrors_non_intel_no_arch(self, m_get_architecture):
        arch = 'ppc64el'
        m_get_architecture.return_value = arch
        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, apt_config.get_default_mirrors())

    def test_get_default_mirrors_non_intel_with_arch(self):
        found = apt_config.get_default_mirrors('ppc64el')

        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, found)

    def test_mirror_arches_sysdefault(self):
        """test_mirror_arches - Test arches falling back to sys default"""
        arch = distro.get_architecture()
        default_mirrors = apt_config.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        cfg = {"primary": [{'arches': ["thisarchdoesntexist_64"],
                            "uri": "notthis"},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthiseither"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["thisarchdoesntexist_64"],
                             "uri": "nothateither"}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_mirror_search(self):
        """test_mirror_search - Test searching mirrors in a list
            mock checks to avoid relying on network connectivity"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "search": ["pfailme", pmir]}],
               "security": [{'arches': ["default"],
                             "search": ["sfailme", smir]}]}

        with mock.patch.object(apt_config, 'search_for_mirror',
                               side_effect=[pmir, smir]) as mocksearch:
            mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        calls = [call(["pfailme", pmir]),
                 call(["sfailme", smir])]
        mocksearch.assert_has_calls(calls)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_search_many2(self):
        """test_mirror_search_many3 - Test both mirrors specs at once"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir,
                            "search": ["pfailme", "foo"]}],
               "security": [{'arches': ["default"],
                             "uri": smir,
                             "search": ["sfailme", "bar"]}]}

        arch = 'amd64'

        # should be called only once per type, despite two mirror configs
        with mock.patch.object(apt_config, 'get_mirror',
                               return_value="http://mocked/foo") as mockgm:
            mirrors = apt_config.find_apt_mirror_info(cfg, arch)
        calls = [call(cfg, 'primary', arch), call(cfg, 'security', arch)]
        mockgm.assert_has_calls(calls)

        # should not be called, since primary is specified
        with mock.patch.object(apt_config, 'search_for_mirror') as mockse:
            mirrors = apt_config.find_apt_mirror_info(cfg, arch)
        mockse.assert_not_called()

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_url_resolvable(self):
        """test_url_resolvable - Test resolving urls"""

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mockresolve.assert_called_with("1.2.3.4")

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
        mockresolve.assert_called_with("us.archive.ubuntu.com")

        bad = [(None, None, None, "badname", ["10.3.2.1"])]
        good = [(None, None, None, "goodname", ["10.2.3.4"])]
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad, bad, good,
                                            good]) as mocksock:
            ret = util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
            ret2 = util.is_resolvable_url("http://1.2.3.4/ubuntu")
        calls = [call('does-not-exist.example.com.', None, 0, 0, 1, 2),
                 call('example.invalid.', None, 0, 0, 1, 2),
                 call('us.archive.ubuntu.com', None),
                 call('1.2.3.4', None)]
        mocksock.assert_has_calls(calls)
        self.assertTrue(ret)
        self.assertTrue(ret2)

        # side effect need only bad ret after initial call
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad]) as mocksock:
            ret3 = util.is_resolvable_url("http://failme.com/ubuntu")
        calls = [call('failme.com', None)]
        mocksock.assert_has_calls(calls)
        self.assertFalse(ret3)

    def test_disable_suites(self):
        """test_disable_suites - disable_suites with many configurations"""
        release = "xenial"

        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""

        # disable nothing
        disabled = []
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable release suite
        disabled = ["$RELEASE"]
        expect = """# deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable other suite
        disabled = ["$RELEASE-updates"]
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # multi disable
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # multi line disable (same suite multiple times in input)
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
# deb http://UBUNTU.com//ubuntu xenial-updates main
# deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # comment in input
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
#deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
# deb http://UBUNTU.com//ubuntu xenial-updates main
# deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable custom suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ foobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
# deb http://ubuntu.com/ubuntu/ foobar main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable non existing suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite with option
        disabled = ["$RELEASE-updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite with more options and auto $RELEASE expansion
        disabled = ["updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b c=d] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb [a=b c=d] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite while options at others
        disabled = ["$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

    def test_disable_suites_blank_lines(self):
        """test_disable_suites_blank_lines - ensure blank lines allowed"""
        rel = "trusty"

        orig = """
deb http://example.com/mirrors/ubuntu trusty main universe

deb http://example.com/mirrors/ubuntu trusty-updates main universe

deb http://example.com/mirrors/ubuntu trusty-proposed main universe

#comment here"""
        expect = """
deb http://example.com/mirrors/ubuntu trusty main universe

deb http://example.com/mirrors/ubuntu trusty-updates main universe

# deb http://example.com/mirrors/ubuntu trusty-proposed main universe

#comment here"""
        disabled = ["proposed"]
        result = apt_config.disable_suites(disabled, entryify(orig), rel)
        self.assertEqual(expect, lineify(result))

    def test_disable_components(self):
        orig = """\
deb http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial-security \
main restricted universe multiverse
deb-src http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed \
main restricted universe multiverse"""
        expect = orig

        # no-op
        disabled = []
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # no-op 2
        disabled = None
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # we don't disable main
        disabled = ('main', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # nonsense
        disabled = ('asdf', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # free-only
        expect = """\
# deb http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial main universe
# deb http://ubuntu.com/ubuntu xenial-updates main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates main universe
# deb http://ubuntu.com/ubuntu xenial-security main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu xenial-security main universe
# deb-src http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb-src http://ubuntu.com/ubuntu xenial main universe
# deb http://ubuntu.com/ubuntu/ xenial-proposed main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main universe"""
        disabled = ('restricted', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # skip line when this component is the last
        orig = """\
deb http://ubuntu.com/ubuntu xenial main universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates universe
deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        expect = """\
# deb http://ubuntu.com/ubuntu xenial main universe multiverse
deb http://ubuntu.com/ubuntu xenial main
# deb http://ubuntu.com/ubuntu xenial-updates universe
# deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        disabled = ('universe', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # comment everything
        orig = """\
deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        expect = """\
# deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        disabled = ('universe', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # double-hash comment
        orig = """\

## Major bug fix updates produced after the final release of the
## distribution.

deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted
# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted"""
        expect = """\

## Major bug fix updates produced after the final release of the
## distribution.

# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted
deb http://archive.ubuntu.com/ubuntu/ impish-updates main
# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted"""
        disabled = ('restricted', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

    @mock.patch("curtin.util.write_file")
    @mock.patch("curtin.distro.get_architecture")
    def test_generate_with_options(self, get_arch, write_file):
        get_arch.return_value = "amd64"
        orig = """deb http://ubuntu.com//ubuntu $RELEASE main
# stuff things

deb http://ubuntu.com//ubuntu $RELEASE-updates main
deb http://ubuntu.com//ubuntu $RELEASE-security main
deb-src http://ubuntu.com//ubuntu $RELEASE universe multiverse
# deb http://ubuntu.com/ubuntu/ $RELEASE-proposed main
deb [a=b] http://ubuntu.com/ubuntu/ $RELEASE-backports main
"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# stuff things

deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu xenial universe multiverse
# deb http://ubuntu.com/ubuntu/ xenial-proposed main
# deb [a=b] http://ubuntu.com/ubuntu/ $RELEASE-backports main
"""
        # $RELEASE in backports doesn't get expanded because the line is
        # considered invalid because of the options.  So when the line
        # gets commented out, it comments out the original line, not
        # what we've modifed it to.
        rel = 'xenial'
        mirrors = {'PRIMARY': 'http://ubuntu.com/ubuntu/'}

        cfg = {
            'preserve_sources_list': False,
            'sources_list': orig,
            'disable_suites': ['backports'],
        }

        apt_config.generate_sources_list(cfg, rel, mirrors, self.target)
        filepath = os.path.join(self.target, 'etc/apt/sources.list')
        write_file.assert_called_with(filepath, expect, mode=0o644)


class TestDebconfSelections(CiTestCase):

    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    def test_no_set_sel_if_none_to_set(self, m_set_sel):
        apt_config.apply_debconf_selections({'foo': 'bar'})
        m_set_sel.assert_not_called()

    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_set_sel_call_has_expected_input(self, m_get_inst, m_set_sel):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1')}
        lines = '\n'.join(data.values()).split('\n')

        m_get_inst.return_value = ["adduser", "apparmor"]
        m_set_sel.return_value = None

        apt_config.apply_debconf_selections({'debconf_selections': data})
        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_set_sel.call_count, 1)

        # assumes called with *args value.
        selections = m_set_sel.call_args_list[0][0][0].decode()

        missing = [line for line in lines
                   if line not in selections.splitlines()]
        self.assertEqual([], missing)

    @mock.patch("curtin.commands.apt_config.dpkg_reconfigure")
    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_reconfigure_if_intersection(self, m_get_inst, m_set_sel,
                                         m_dpkg_r):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1'),
            'cloud-init': ('cloud-init cloud-init/datasources'
                           'multiselect MAAS')}

        m_set_sel.return_value = None
        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']

        apt_config.apply_debconf_selections({'debconf_selections': data})

        # reconfigure should be called with the intersection
        # of (packages in config, packages installed)
        self.assertEqual(m_dpkg_r.call_count, 1)
        # assumes called with *args (dpkg_reconfigure([a,b,c], target=))
        packages = m_dpkg_r.call_args_list[0][0][0]
        self.assertEqual(set(['cloud-init', 'pkgb']), set(packages))

    @mock.patch("curtin.commands.apt_config.dpkg_reconfigure")
    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_reconfigure_if_no_intersection(self, m_get_inst, m_set_sel,
                                            m_dpkg_r):
        data = {'set1': 'pkga pkga/q1 mybool false'}

        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']
        m_set_sel.return_value = None

        apt_config.apply_debconf_selections({'debconf_selections': data})

        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_dpkg_r.call_count, 0)

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_does_reconfigure(self, m_subp):
        target = "/foo-target"

        # due to the way the cleaners are called (via dictionary reference)
        # mocking clean_cloud_init directly does not work.  So we mock
        # the CONFIG_CLEANERS dictionary and assert our cleaner is called.
        ci_cleaner = mock.MagicMock()
        with mock.patch.dict("curtin.commands.apt_config.CONFIG_CLEANERS",
                             values={'cloud-init': ci_cleaner}, clear=True):
            apt_config.dpkg_reconfigure(['pkga', 'cloud-init'],
                                        target=target)
        # cloud-init is actually the only package we have a cleaner for
        # so for now, its the only one that should reconfigured
        self.assertTrue(m_subp.called)
        ci_cleaner.assert_called_with(target)
        self.assertEqual(m_subp.call_count, 1)
        found = m_subp.call_args_list[0][0][0]
        expected = ['dpkg-reconfigure', '--frontend=noninteractive',
                    'cloud-init']
        self.assertEqual(expected, found)

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_not_done_on_no_data(self, m_subp):
        apt_config.dpkg_reconfigure([])
        m_subp.assert_not_called()

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_not_done_if_no_cleaners(self, m_subp):
        apt_config.dpkg_reconfigure(['pkgfoo', 'pkgbar'])
        m_subp.assert_not_called()

# vi: ts=4 expandtab syntax=python
