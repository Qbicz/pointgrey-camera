# coding=utf-8
# =============================================================================
#  Copyright © 2017 FLIR Integrated Imaging Solutions, Inc. All Rights Reserved.
#
#  This software is the confidential and proprietary information of FLIR
#  Integrated Imaging Solutions, Inc. ("Confidential Information"). You
#  shall not disclose such Confidential Information and shall use it only in
#  accordance with the terms of the license agreement you entered into
#  with FLIR Integrated Imaging Solutions, Inc. (FLIR).
#
#  FLIR MAKES NO REPRESENTATIONS OR WARRANTIES ABOUT THE SUITABILITY OF THE
#  SOFTWARE, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
#  PURPOSE, OR NON-INFRINGEMENT. FLIR SHALL NOT BE LIABLE FOR ANY DAMAGES
#  SUFFERED BY LICENSEE AS A RESULT OF USING, MODIFYING OR DISTRIBUTING
#  THIS SOFTWARE OR ITS DERIVATIVES.
# =============================================================================

import PySpin
import datetime, threading, time


mutex_cam = threading.Lock()


def timer_trigger(cam, nodemap, nodemap_tldevice, interval=1):
    """
        Trigger image capture after interval. By default each 1 second.
    """

    next_call = time.time()
    while True:
        print 'Trigger image -', datetime.datetime.now()
        next_call = next_call + interval;

        acquire_images(cam, nodemap, nodemap_tldevice)

        # Sleep in this thread until next time interval
        time.sleep(next_call - time.time())

def timer_trigger_start(cam, nodemap, nodemap_tldevice):
    """
        Start image triggering.
    """
    timerThread = threading.Thread(target=timer_trigger, args=(cam, nodemap, nodemap_tldevice))
    timerThread.daemon = True
    timerThread.start()





def acquire_images(cam, nodemap, nodemap_tldevice):
    """
    This function acquires and saves images from a device.

    :param cam: Camera to acquire images from.
    :param nodemap: Device nodemap.
    :param nodemap_tldevice: Transport layer device nodemap.
    :type cam: CameraPtr
    :type nodemap: INodeMap
    :type nodemap_tldevice: INodeMap
    :return: True if successful, False otherwise.
    :rtype: bool
    """

    global mutex_cam

    print 'Waiting for mutex...'
    mutex_available = mutex_cam.acquire(blocking=False)
    if mutex_available == False:
        print 'Mutex occupied!'
        return False
    print 'Acquired mutex!'

    print "*** IMAGE ACQUISITION ***\n"
    try:
        result = True

        # Set acquisition mode to continuous
        # In order to access the node entries, they have to be casted to a pointer type (CEnumerationPtr here)
        node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
        if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
            print "Unable to set acquisition mode to continuous (enum retrieval). Aborting..."
            return False

        # Retrieve entry node from enumeration node
        node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName("Continuous")
        if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
                node_acquisition_mode_continuous):
            print "Unable to set acquisition mode to continuous (entry retrieval). Aborting..."
            return False

        # Retrieve integer value from entry node
        acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

        # Set integer value from entry node as new value of enumeration node
        node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

        print "Acquisition mode set to continuous..."

        #  Begin acquiring images
        cam.BeginAcquisition()

        print "Acquiring images..."

        #  Retrieve device serial number for filename
        #
        #  *** NOTES ***
        #  The device serial number is retrieved in order to keep cameras from
        #  overwriting one another. Grabbing image IDs could also accomplish
        #  this.
        device_serial_number = ""
        node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode("DeviceSerialNumber"))
        if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
            device_serial_number = node_device_serial_number.GetValue()
            print "Device serial number retrieved as %s..." % device_serial_number

        image_count = 0

        # Retrieve, convert, and save images
        while True:
            try:
                #  Retrieve the next image from the trigger
                result &= grab_next_image_by_trigger(nodemap, cam)

                #  Retrieve next received image
                image_result = cam.GetNextImage()

                #  Ensure image completion
                if image_result.IsIncomplete():
                    print "Image incomplete with image status %d ..." % image_result.GetImageStatus()

                else:

                    #  Print image information; height and width recorded in pixels
                    #
                    #  *** NOTES ***
                    #  Images have quite a bit of available metadata including
                    #  things such as CRC, image status, and offset values, to
                    #  name a few.
                    width = image_result.GetWidth()
                    height = image_result.GetHeight()
                    print "Grabbed Image %d, width = %d, height = %d" % (image_count, width, height)

                    #  Convert image to RGB 8-bit
                    #
                    #  *** NOTES ***
                    #  Images can be converted between pixel formats by using
                    #  the appropriate enumeration value. Unlike the original
                    #  image, the converted one does not need to be released as
                    #  it does not affect the camera buffer.
                    #
                    #  When converting images, color processing algorithm is an
                    #  optional parameter.
                    image_converted = image_result.Convert(PySpin.PixelFormat_RGB8, PySpin.HQ_LINEAR)

                    # Create a unique filename
                    if device_serial_number:
                        filename = "Trigger-%s-%d.jpg" % (device_serial_number, image_count)
                    else:  # if serial number is empty
                        filename = "Trigger-%d.jpg" % image_count

                    # Save image
                    #
                    #  *** NOTES ***
                    #  The standard practice of the examples is to use device
                    #  serial numbers to keep images of one device from
                    #  overwriting those of another.
                    image_converted.Save(filename)
                    print "Image saved at %s" % filename

                    #  Release image
                    #
                    #  *** NOTES ***
                    #  Images retrieved directly from the camera (i.e. non-converted
                    #  images) need to be released in order to keep from filling the
                    #  buffer.
                    image_result.Release()
                    image_count += 1
                    print ""

            except PySpin.SpinnakerException as ex:
                print "Error: %s" % ex
                return False

        # End acquisition
        #
        #  *** NOTES ***
        #  Ending acquisition appropriately helps ensure that devices clean up
        #  properly and do not need to be power-cycled to maintain integrity.
        cam.EndAcquisition()

    except PySpin.SpinnakerException as ex:
        print "Error: %s" % ex
        mutex_cam.release()
        return False

    mutex_cam.release()
    print 'Released mutex.'

    return result


def run_single_camera(cam):
    """
    This function acts as the body of the example; please see NodeMapInfo example
    for more in-depth comments on setting up cameras.

    :param cam: Camera to run on.
    :type cam: CameraPtr
    :return: True if successful, False otherwise.
    :rtype: bool
    """
    try:
        result = True
        err = False

        # Retrieve TL device nodemap and print device information
        nodemap_tldevice = cam.GetTLDeviceNodeMap()

        result &= print_device_info(nodemap_tldevice)

        # Initialize camera
        cam.Init()

        # Retrieve GenICam nodemap
        nodemap = cam.GetNodeMap()

        timer_trigger_start(cam, nodemap, nodemap_tldevice)
        print 'Timer trigger started for current camera'

        # Acquire images
        result &= acquire_images(cam, nodemap, nodemap_tldevice)

        # Deinitialize camera
        cam.DeInit()

    except PySpin.SpinnakerException as ex:
        print "Error: %s" % ex
        result = False

    return result


def main():
    """
    Example entry point; please see Enumeration example for more in-depth
    comments on preparing and cleaning up the system.

    :return: True if successful, False otherwise.
    :rtype: bool
    """
    # Retrieve singleton reference to system object
    system = PySpin.System.GetInstance()

    # Retrieve list of cameras from the system
    cam_list = system.GetCameras()

    num_cameras = cam_list.GetSize()

    print "Number of cameras detected: %d" % num_cameras

    # Finish if there are no cameras
    if num_cameras == 0:
        # Clear camera list before releasing system
        cam_list.Clear()

        # Release system
        system.ReleaseInstance()

        print "Not enough cameras!"
        raw_input("Done! Press Enter to exit...")
        return False

    # Run example on each camera
    for i in range(num_cameras):
        cam = cam_list.GetByIndex(i)

        print "Running example for camera %d..." % i

        result = run_single_camera(cam)
        print "Camera %d example complete... \n" % i

    # Release reference to camera
    # NOTE: Unlike the C++ examples, we cannot rely on pointer objects being automatically
    # cleaned up when going out of scope.
    # The usage of del is preferred to assigning the variable to None.
    del cam

    # Clear camera list before releasing system
    cam_list.Clear()

    # Release instance
    system.ReleaseInstance()

    raw_input("Done! Press Enter to exit...")
    return result


if __name__ == "__main__":
    main()
