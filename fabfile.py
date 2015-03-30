"""A setup system for Zabbix hosts """

from fabric.api import local, get, hide, prompt, settings, task
from fabric.network import disconnect_all
from contextlib import contextmanager
import os
import platform
import glob
import re

REMOTE_DEPOT = '/var/depot/'
WIN_LOCAL_BIN = 'C:\\bin\\'
WIN_ZABBIX_BIN = WIN_LOCAL_BIN + 'zabbix\\'
WIN_LOCAL_CONF = 'C:\\etc\\'
WIN_ZABBIX_CONF = WIN_LOCAL_CONF + 'zabbix\\'
WIN_LOCAL_LOG = 'C:\\var\\log\\'
WIN_ZABBIX_LOG = WIN_LOCAL_LOG + 'zabbix\\'
# Super hack until we get a which function
MACOS_ZABBIX_DIR = '/opt/boxen/homebrew/Cellar/zabbix/2.2.2/'
MACOS_ETC = '/usr/local/etc'


@contextmanager
def _mute():
    """Run a fabric command without reporting any responses to the user. """
    with settings(warn_only='true'):
        with hide('running', 'stdout', 'stderr', 'warnings'):
            yield


def _header(txt):
    """Decorate a string to make it stand out as a header. """
    wrapper = """
-------------------------------------------------------------------------------
"""
    return wrapper.strip() + "\n" + txt + "\n" + wrapper.strip()


def sed_bin():
    if platform.system() == 'Darwin':
        sed = '/usr/bin/sed'
    if platform.system() == 'Windows':
        sed = WIN_LOCAL_BIN + 'sed.exe'
    return sed


def sed_check():
    """Unused """
    if not os.path.exists(sed_bin()):
        print "Installing Sed"
        install_exe('sed.exe')
    else:
        print "Sed is already installed"


@task
def install():
    """Download and install the Zabbix agent

    """
    if platform.system() == 'Darwin':
        install_mac()
    else:
        install_windows()


def install_mac():
    """Use homebrew to install the Zabbix Agent on a Mac

    Homebrew downloads the agent from SourceForge

    TODO: Check if Homebrew is present
    """
    print
    print _header("Installing the Zabbix agent")
    local('brew install zabbix --agent-only')


def install_windows():
    """Download and install Zabbix agent on Windows

    Downloads the Zabbix installer from the software depot.
    Moves binaries and config files into place.
    """
    # Get a tool for extracting the download
    print
    print _header("Checking for dependencies")
    extract_bin = WIN_LOCAL_BIN + '7za.exe'
    if not os.path.exists(extract_bin):
        print "Installing 7zip"
        install_exe('7zip.exe')
    else:
        print "7zip is already installed"
    print

    # Download the zabbix agent
    print _header("Getting Zabbix from the depot")
    zabbix_archive_name = 'zabbix_agents_2.0.4.win.zip'
    zabbix_archive_remote = REMOTE_DEPOT + zabbix_archive_name
    with _mute():
        get(zabbix_archive_remote, local_temp())
    print 'Zabbix downloaded successfully'
    # Disconnect now that we're done downloading things from the depot
    disconnect_all()

    print
    print _header("Extracting Zabbix on the local system")
    extract_zabbix = extract_bin + ' ' + \
        'x %temp%\\' + zabbix_archive_name + ' ' + \
        '-o' + WIN_ZABBIX_BIN
    with _mute():
        local(extract_zabbix)
    print 'Zabbix extracted successfully'

    print
    print _header("Moving the correct executables into place")
    with _mute():
        keep = get_architecture()
        local('move ' + WIN_ZABBIX_BIN + 'bin\\win' + keep + '\* ' +
              WIN_ZABBIX_BIN)
        rmdir_cmd = 'rmdir /Q /S'
        local(rmdir_cmd + ' ' + WIN_ZABBIX_BIN + 'bin\\')
    print "The Zabbix " + keep + "bit EXEs are installed at " + WIN_ZABBIX_BIN


def check_conf():
    """Check to see if a conf already exists

    TODO: Windows
    """
    if platform.system() == 'Darwin':
        if os.path.exists(MACOS_ETC + os.sep + 'zabbix_agentd.conf'):
            return True


def init_conf():
    print
    print _header("Initializing agent config files")

    if platform.system() == 'Darwin':
        if not os.path.exists(MACOS_ETC):
            local('mkdir ' + MACOS_ETC)
        conf_file = MACOS_ETC + os.sep + 'zabbix_agentd.conf'
        local('cp ' + os.path.dirname(os.path.abspath(__file__)) + os.sep +
              'zabbix_agentd_osx.conf ' + conf_file)
    if platform.system() == 'Windows':
        conf_file = WIN_ZABBIX_CONF + 'zabbix_agentd.conf'
        with _mute():
            if not os.path.exists(WIN_ZABBIX_CONF):
                local('mkdir ' + WIN_ZABBIX_CONF)
                local('move ' + WIN_ZABBIX_BIN +
                      'conf\\zabbix_agentd.win.conf ' + conf_file)
                rmdir_cmd = 'rmdir /Q /S'
                local(rmdir_cmd + ' ' + WIN_ZABBIX_BIN + 'conf')
        # Write the log config path in the Zabbix conf
        # TODO put this in it's on func
        with _mute():
            if not os.path.exists(WIN_ZABBIX_LOG):
                local('mkdir ' + WIN_ZABBIX_LOG)
    print "The Zabbix config file is at " + conf_file

    return conf_file


@task
def configure():
    """Configure Zabbix agent

    Sets up common and custom configurations.
    Starts the Zabbix monitor.
    """
    print
    print _header("Configuring Zabbix")

    if check_conf():
        continue_prompt = """
A configuration file already exists. Do you want to proceed?
This will destroy your existing settings.
y/n
default = """
        proceed = prompt(continue_prompt, default='n')
        if proceed == 'n':
            exit()
        if proceed == 'y':
            conf_file = init_conf()
        else:
            exit()
    else:
        conf_file = init_conf()

    # Ask for the name of the Zabbix server
    server_prompt = """
What is IP of the central Zabbix server?
default = """
    zabbix_server = prompt(server_prompt, default='127.0.0.1')
    with _mute():
        local(sed_bin() + ' ' + '"s/^Server=127.0.0.1$/' +
              'Server=' + zabbix_server + '/g" ' + conf_file +
              ' >' + conf_file + '.01')

    # Ask for a hostname. This must be the same as the host name setup on
    # the Zabbix server
    print
    hostname_prompt = """
What would you like to call this computer in the Zabbix system?

In Zabbix parlance this is called the 'hostname'
 - It must be unique and is case sensitive
 - It must match the configured host on the Zabbix Server
 - Allowed characters: alphanumeric, '.', ' ', '_' and '-'.
 - Maximum length: 64
default = """
    zabbix_hostname = prompt(hostname_prompt, default=computer_hostname())
    with _mute():
        if platform.system() == 'Windows':
            local(sed_bin() + ' ' + '"s/^Hostname=Windows\ host$/' +
                  'Hostname=' + zabbix_hostname + '/g" ' + conf_file + '.01'
                  ' >' + conf_file + '.02')
        if platform.system() == 'Darwin':
            local(sed_bin() + ' ' + '"s/^Hostname=Zabbix\ server$/' +
                  'Hostname=' + zabbix_hostname + '/g" ' + conf_file + '.01'
                  ' >' + conf_file + '.02')

    # Get rid of the temporary sed files
    with _mute():
        if platform.system() == 'Darwin':
            local('rm ' + conf_file + '.01')
            local('mv ' + conf_file + '.02 ' + conf_file)
        if platform.system() == 'Windows':
            local('del /Q ' + conf_file + '.01')
            local('move /Y ' + conf_file + '.02 ' + conf_file)

    # Copy the Launch Agent in place
    # This will cause the Zabbix Agent to start on boot
    if platform.system() == 'Darwin':
        sudo_prompt = """
The system may need your password to run sudo commands.
default = """
        print
        print sudo_prompt
        local('sudo cp com.zabbix.zabbix_agentd.plist \
              ~/Library/LaunchAgents/com.zabbix.zabbix_agentd.plist')


@task
def start():
    """WIN only - Start the Zabbix agent

    TODO - MACOS version
    """
    conf_file = init_conf()
    print
    print _header("Launching the Zabbix agent")
    local(WIN_ZABBIX_BIN + 'zabbix_agentd.exe --config ' + conf_file +
          ' --install')
    local(WIN_ZABBIX_BIN + 'zabbix_agentd.exe --config ' + conf_file +
          ' --start')


@task
def uninstall():
    """WIN only - Uninstall Zabbix

    This will remove the Zabbix files, stop the Zabbix service, and
    delete the Zabbix service.
    """
    print
    print _header("Uninstall the Zabbix service")
    with _mute():
        zabbix_service_state = service_installed()
    # Stop the service if it's running first
    if 4 in zabbix_service_state:
        local(WIN_ZABBIX_BIN + 'zabbix_agentd.exe --stop \
                          --config=' + WIN_ZABBIX_CONF + 'zabbix_agentd.conf')
        print "Stopping the Zabbix service."
    # Delete the service
    if 1 in zabbix_service_state:
        local(WIN_ZABBIX_BIN + 'zabbix_agentd.exe --uninstall \
                          --config=' + WIN_ZABBIX_CONF + 'zabbix_agentd.conf')
        print "Deleting the Zabbix service."
    if 0 in zabbix_service_state:
        print "No Zabbix service was found to uninstall."

    print
    print _header("Remove the Zabbix configuration and executable files")
    rmdir_cmd = 'rmdir /Q /S'
    rm_cmd = 'del /Q'
    uninstalled = False
    paths = [WIN_ZABBIX_BIN + 'bin',
             WIN_ZABBIX_BIN + 'conf',
             WIN_ZABBIX_CONF]
    paths.extend(glob.glob(WIN_ZABBIX_BIN + '*.exe'))

    for filepath in paths:
        if os.path.isfile(filepath):
            local(rm_cmd + ' ' + filepath)
            uninstalled = True
        if os.path.isdir(filepath):
            local(rmdir_cmd + ' ' + filepath)
            uninstalled = True

    if os.path.isdir(WIN_ZABBIX_LOG):
        log_message = """
A Zabbix log folder exists at %s but we are not deleting it,
since it may contain historical information that we don't want to loose.
"""
        print log_message % WIN_ZABBIX_LOG

    print
    if uninstalled:
        print _header('Zabbix is uninstalled.')
    else:
        print _header('There are no files to uninstall.')


@task
def service_installed():
    """WIN only - Determine whether the Zabbix service is installed and running

    Returns:
        A dictionary of a service state and explanatory message
    """
    with _mute():
        try:
            zabbix_srvc_info = local('sc query "Zabbix Agent"', capture=True)
            regex = re.compile("STATE[^:]*: *([\d]*)", re.MULTILINE)
            r = regex.search(zabbix_srvc_info)
            state_int = int(r.group(1))
            if state_int == 1:
                state = {state_int:
                         "Zabbix is installed but is currently stopped."}
            if state_int == 4:
                state = {state_int:
                         "Zabbix is installed and currently running."}
        except:
            state = {0, "Zabbix isn't installed as service."}
    for _, value in state.iteritems():
        print value
    return state


def computer_hostname():
    """Return the computer's hostname"""
    with _mute():
        return local('hostname', capture=True)


def get_architecture():
    """Get the local system CPU architecture

    Returns: A string of either 32 or 64.
    """
    arch = local('wmic OS get OSArchitecture', capture=True)
    if '64' in arch:
        return '64'
    else:
        return '32'


def install_exe(exe):
    """Get an exe from the depot and place it in the local bin"""
    get(REMOTE_DEPOT + exe, WIN_LOCAL_BIN)


def local_temp():
    """Get the Windows temp folder

    Returns: The temp folder path as a string.
    """
    with _mute():
        local_temp = local('echo %temp%', capture=True)
        return local_temp
