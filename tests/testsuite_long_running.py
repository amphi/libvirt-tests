import unittest

# Following import statement allows for proper python IDE support and proper
# nix build support. The duplicate listing of imported functions is a bit
# unfortunate, but it seems to be the best compromise. This way the python IDE
# support works out of the box in VSCode and IntelliJ without requiring
# additional IDE configuration.
try:
    from ..test_helper.test_helper import (  # type: ignore
        LibvirtTestsBase,
        number_of_devices,
        initialControllerVMSetup,
        initialComputeVMSetup,
        wait_for_guest_pci_device_enumeration,
        wait_for_ssh,
    )
except Exception:
    from test_helper import (
        LibvirtTestsBase,
        number_of_devices,
        initialControllerVMSetup,
        initialComputeVMSetup,
        wait_for_guest_pci_device_enumeration,
        wait_for_ssh,
    )

# pyright: reportPossiblyUnboundVariable=false

# Following is required to allow proper linting of the python code in IDEs.
# Because certain functions like start_all() and certain objects like computeVM
# or other machines are added by Nix, we need to provide certain stub objects
# in order to allow the IDE to lint the python code successfully.
if "start_all" not in globals():
    from ..test_helper.test_helper.nixos_test_stubs import (  # type: ignore
        computeVM,
        controllerVM,
        start_all,
    )

# Paths where we can find the libvirt domain configuration XML files
DOMAIN_DEF_PERSISTENT_PATH = "/var/lib/libvirt/ch/testvm.xml"
DOMAIN_DEF_TRANSIENT_PATH = "/var/run/libvirt/ch/testvm.xml"


class LibvirtTests(LibvirtTestsBase):  # type: ignore
    def __init__(self, methodName):
        super().__init__(methodName, controllerVM, computeVM)

    @classmethod
    def setUpClass(cls):
        start_all()
        initialControllerVMSetup(controllerVM)
        initialComputeVMSetup(computeVM)

    def test_often_attach_and_detach(self):
        """
        This test attaches and detaches network devices 400 times. The reason is
        that this failed at around 340 attach/detach cycles when Cloud Hypervisor
        didn't free GSIs
        """
        controllerVM.succeed("virsh define /etc/domain-chv.xml")
        controllerVM.succeed("virsh start testvm")
        wait_for_ssh(controllerVM)

        # We have to attach and detach often. Thus to speed things up, we do
        # not use the hotplug-function, which always checks that the attach or
        # detach did succeed.
        num_hotplugs = 0
        num_devices = 20

        def hotplug_often():
            nonlocal num_hotplugs
            num_old = number_of_devices(controllerVM)

            for i in range(0, num_devices):
                num_hotplugs += 1
                command = f"virsh attach-interface --target l33t_n{num_hotplugs:03d} --type network --source libvirt-testnetwork --mac DE:AD:BE:EF:13:{i:02d} --model virtio testvm"
                controllerVM.succeed(command)

            wait_for_guest_pci_device_enumeration(controllerVM, num_old + num_devices)

        def unplug_often():
            num_old = number_of_devices(controllerVM)

            for i in range(0, num_devices):
                command = f"virsh detach-interface testvm network --mac DE:AD:BE:EF:13:{i:02d}"
                controllerVM.succeed(command)

            wait_for_guest_pci_device_enumeration(controllerVM, num_old - num_devices)

        desired_hotplugs = 400
        for _ in range(0, int(desired_hotplugs / num_devices)):
            hotplug_often()
            unplug_often()


def suite():
    # Test cases sorted in alphabetical order.
    testcases = [
        LibvirtTests.test_often_attach_and_detach,
    ]

    suite = unittest.TestSuite()
    for testcaseMethod in testcases:
        suite.addTest(LibvirtTests(testcaseMethod.__name__))
    return suite


runner = unittest.TextTestRunner()
if not runner.run(suite()).wasSuccessful():
    raise Exception("Test Run unsuccessful")
