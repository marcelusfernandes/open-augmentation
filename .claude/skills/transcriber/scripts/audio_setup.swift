import CoreAudio
import Foundation

let MULTI_OUTPUT_NAME = "BlackHole + Speakers"
let MULTI_OUTPUT_UID = "com.augmentation.blackhole-speakers"

// MARK: - Helpers

func systemObject() -> AudioObjectID { AudioObjectID(kAudioObjectSystemObject) }

func getProperty<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, default defaultValue: T) -> T {
    var address = AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size = UInt32(MemoryLayout<T>.size)
    var value = defaultValue
    AudioObjectGetPropertyData(object, &address, 0, nil, &size, &value)
    return value
}

func getDevices() -> [AudioDeviceID] {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var dataSize: UInt32 = 0
    AudioObjectGetPropertyDataSize(systemObject(), &address, 0, nil, &dataSize)
    let count = Int(dataSize) / MemoryLayout<AudioDeviceID>.size
    var devices = [AudioDeviceID](repeating: 0, count: count)
    AudioObjectGetPropertyData(systemObject(), &address, 0, nil, &dataSize, &devices)
    return devices
}

func getString(_ device: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> String {
    var address = AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = UInt32(MemoryLayout<CFString?>.size)
    var ptr: Unmanaged<CFString>?
    let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &ptr)
    if status != 0 { return "" }
    return ptr?.takeRetainedValue() as String? ?? ""
}

func getDeviceName(_ id: AudioDeviceID) -> String { getString(id, kAudioObjectPropertyName) }
func getDeviceUID(_ id: AudioDeviceID) -> String { getString(id, kAudioDevicePropertyDeviceUID) }

func findDeviceByName(_ needle: String) -> AudioDeviceID? {
    let lower = needle.lowercased()
    return getDevices().first { getDeviceName($0).lowercased().contains(lower) }
}

func setDefaultOutput(_ device: AudioDeviceID) -> Bool {
    var deviceID = device
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDefaultOutputDevice,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    let status = AudioObjectSetPropertyData(
        systemObject(), &address, 0, nil,
        UInt32(MemoryLayout<AudioDeviceID>.size), &deviceID
    )
    return status == 0
}

func currentDefaultOutput() -> AudioDeviceID {
    getProperty(systemObject(), kAudioHardwarePropertyDefaultOutputDevice, default: AudioDeviceID(0))
}

// MARK: - Commands

func cmdCreateMultiOutput() -> Int32 {
    if let existing = findDeviceByName(MULTI_OUTPUT_NAME) {
        print("Multi-Output already exists: '\(getDeviceName(existing))' (id \(existing))")
        return 0
    }

    guard let blackhole = findDeviceByName("blackhole") else {
        print("ERROR: BlackHole device not found. Install BlackHole 2ch first.")
        return 1
    }
    guard let speakers = findDeviceByName("MacBook Pro Speakers") else {
        print("ERROR: MacBook Pro Speakers not found.")
        return 1
    }

    let blackholeUID = getDeviceUID(blackhole)
    let speakersUID = getDeviceUID(speakers)

    let dict: [String: Any] = [
        kAudioAggregateDeviceNameKey as String: MULTI_OUTPUT_NAME,
        kAudioAggregateDeviceUIDKey as String: MULTI_OUTPUT_UID,
        kAudioAggregateDeviceMasterSubDeviceKey as String: speakersUID,
        kAudioAggregateDeviceIsStackedKey as String: 1,  // 1 = Multi-Output (stacked), 0 = Aggregate
        kAudioAggregateDeviceSubDeviceListKey as String: [
            [
                kAudioSubDeviceUIDKey as String: speakersUID,
                kAudioSubDeviceDriftCompensationKey as String: 0,
            ],
            [
                kAudioSubDeviceUIDKey as String: blackholeUID,
                kAudioSubDeviceDriftCompensationKey as String: 1,
            ],
        ],
    ]

    var aggregateID: AudioDeviceID = 0
    let status = AudioHardwareCreateAggregateDevice(dict as CFDictionary, &aggregateID)
    if status != 0 {
        print("ERROR: AudioHardwareCreateAggregateDevice failed with OSStatus \(status)")
        return 1
    }
    print("Created '\(MULTI_OUTPUT_NAME)' (id \(aggregateID))")
    return 0
}

func cmdSwitchOutput(_ deviceName: String) -> Int32 {
    guard let device = findDeviceByName(deviceName) else {
        print("ERROR: device matching '\(deviceName)' not found.")
        return 1
    }
    let name = getDeviceName(device)
    if setDefaultOutput(device) {
        print("Default output → \(name) (id \(device))")
        return 0
    }
    print("ERROR: failed to switch default output to \(name)")
    return 1
}

func cmdCurrentOutput() -> Int32 {
    let id = currentDefaultOutput()
    print(getDeviceName(id))
    return 0
}

func cmdListDevices() -> Int32 {
    for d in getDevices() {
        let name = getDeviceName(d)
        let uid = getDeviceUID(d)
        if !name.isEmpty {
            print("[\(d)] \(name) — \(uid)")
        }
    }
    return 0
}

// MARK: - Entry point

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("Usage: audio_setup.swift {create-multi-output | switch-output <name> | current-output | list}")
    exit(1)
}

switch args[1] {
case "create-multi-output":
    exit(cmdCreateMultiOutput())
case "switch-output":
    guard args.count >= 3 else { print("Usage: switch-output <name>"); exit(1) }
    exit(cmdSwitchOutput(args[2]))
case "current-output":
    exit(cmdCurrentOutput())
case "list":
    exit(cmdListDevices())
default:
    print("Unknown command: \(args[1])")
    exit(1)
}
