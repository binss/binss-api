import asyncio
import datetime
import platform
import requests
import sys
import time

from bleak import BleakClient, BleakScanner, discover
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

ADDRESS = (
    "50-FB-19-1A-92-C9"
    if platform.system() != "Darwin"
    else "2CB38FA5-0ECF-4754-93E4-25BA352CE582"
)
HISTORY_WEIGHT_CHARACTERISTIC = "00002a2f-0000-3512-2118-0009af100700"

XIAOMI_SCALE_USER_SEX = 'male'
XIAOMI_SCALE_USER_AGE = 20
XIAOMI_SCALE_USER_HEIGHT = 180

API_SERVER_URL = "http://127.0.0.1:10086/xiaomi_scale"
API_SERVER_VERIFY_TOKEN = "testtest"


# Get LBM coefficient with impedance
def GetLBMCoefficient(age, height, weight, impedance):
    lbm = (height * 9.058 / 100) * (height / 100)
    lbm += weight * 0.32 + 12.226
    lbm -= impedance * 0.0068
    lbm -= age * 0.0542
    return lbm


def GetFatPercentage(sex, age, height, weight, impedance):
    # Set a constant to remove from LBM
    if sex == "female" and age <= 49:
        const = 9.25
    elif sex == "female" and age > 49:
        const = 7.25
        const = 4.95  # new
    else:
        const = 0.8

    # Calculate body fat percentage
    LBM = GetLBMCoefficient(age, height, weight, impedance)

    if sex == "male" and weight < 61:
        coefficient = 0.98
    elif sex == "female" and weight > 60:
        coefficient = 0.96
        if height > 160:
            coefficient *= 1.03
    elif sex == "female" and weight < 50:
        coefficient = 1.02
        if height > 160:
            coefficient *= 1.03
    else:
        coefficient = 1.0
    fat_percentage = (1.0 - (((LBM - const) * coefficient) / weight)) * 100

    # Capping body fat percentage
    if fat_percentage > 63:
        fat_percentage = 75
    # return checkValueOverflow(fat_percentage, 5, 75) # do not use, otherwise calculation error
    return fat_percentage

# MiScale Raw Data Schema
# +------+------------------------+
# | byte |        function        |
# +------+------------------------+
# | 0    | Bit 0: unknown         |
# |      | Bit 1: kg unit         |
# |      | Bit 2: lbs unit        |
# |      | Bit 3: jin unit        |
# |      | Bit 4: unknown         |
# |      | Bit 5: stabilized      |
# |      | Bit 6: unknown         |
# |      | Bit 7: load removed    |
# +------+------------------------+
# | 1-2  | weight (little endian) |
# +------+------------------------+
# | 3-4  | year (little endian)   |
# +------+------------------------+
# | 5    | month                  |
# +------+------------------------+
# | 6    | day                    |
# +------+------------------------+
# | 7    | hour                   |
# +------+------------------------+
# | 8    | minute                 |
# +------+------------------------+
# | 9    | second                 |
# +------+------------------------+
def DecodeData(data):
    # size: 13 byte = 26 hex number
    control_byte = data[0]

    is_kg_unit = (control_byte & (1 << 1)) != 0
    is_lbs_unit = (control_byte & (1 << 2)) != 0
    is_jin_unit = (control_byte & (1 << 3)) != 0
    is_stabilized = (control_byte & (1 << 5)) != 0
    load_removed = (control_byte & (1 << 7)) != 0
    # 4 or 6?
    xxx = (control_byte & (1 << 4)) != 0
    xxxx = (control_byte & (1 << 6)) != 0

    # Weight: convert to kg
    measure_weight = int.from_bytes(data[11:13], "little") * 0.01
    if is_kg_unit:
        weight = round(measure_weight * 0.50, 2)
    elif is_lbs_unit:
        weight = round(measure_weight * 0.4536, 2)
    elif is_jin_unit:
        weight = round(measure_weight * 0.5 * 0.5, 2)

    # Impedance
    impedance = int.from_bytes(data[9:11], "little")

    year = int.from_bytes(data[2:4], "little")
    month = int.from_bytes(data[4:5], "little")
    day = int.from_bytes(data[5:6], "little")
    hour = int.from_bytes(data[6:7], "little")
    minute = int.from_bytes(data[7:8], "little")
    second = int.from_bytes(data[8:9], "little")
    datetime = "{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(year, month, day, hour, minute, second)

    fat_percentage = GetFatPercentage(XIAOMI_SCALE_USER_SEX, XIAOMI_SCALE_USER_AGE, XIAOMI_SCALE_USER_HEIGHT, weight, impedance)
    print("Datetime: ", datetime)
    print("Weight(kg)", weight)
    print("Impedance: ", impedance)
    print("Fat Percentage", fat_percentage)
    return {"datetime": datetime, "weight": weight, "impedance": impedance, "fat_percentage": fat_percentage}


queue = asyncio.Queue()

async def HandleRecvData(sender, data):
    await queue.put(data)

async def UploadData(data):
    data["token"] = API_SERVER_VERIFY_TOKEN
    r = requests.post(url = API_SERVER_URL, json = data)
    print("Upload result:", r.text)

async def Detect():
    try:
      async with BleakClient(ADDRESS) as client:
          async def HandleHistoryDataNumber(data):
              record_num = int.from_bytes(data[1:2], "little")
              print("Record num: ", record_num)
              if record_num > 0:
                  await client.write_gatt_char(HISTORY_WEIGHT_CHARACTERISTIC, b"\x02")
              return record_num

          async def HandleHistoryData(data):
              if data == None:
                  return
              info = DecodeData(data)
              await UploadData(info)

          async def ComsumeRecvData():
              while True:
                  data = await queue.get()
                  # print(data)
                  if data is None:
                      print("Finish")
                      break
                  if len(data) == 7:
                      record_num = await HandleHistoryDataNumber(data)
                      if record_num == 0:
                          print("No record to read, stop")
                          break
                  if len(data) == 13:
                      await HandleHistoryData(data)
                  if data == b"\x03":
                      await client.write_gatt_char(HISTORY_WEIGHT_CHARACTERISTIC, b"\x03")
                      # Clear records
                      # await asyncio.sleep(1.0)
                      # await client.write_gatt_char(HISTORY_WEIGHT_CHARACTERISTIC, [0x04, 0xff, 0xff, 0xff, 0xff])
                      print("No more data, stop")
                      break


          print("Connected: ", client.is_connected)

          await client.start_notify(HISTORY_WEIGHT_CHARACTERISTIC, HandleRecvData)
          await client.write_gatt_char(HISTORY_WEIGHT_CHARACTERISTIC, bytearray([0x01, 0xFF, 0xFF, 0xFF, 0xFF]))
          await ComsumeRecvData()
          await client.stop_notify(HISTORY_WEIGHT_CHARACTERISTIC)
    except Exception as e:
        print("Capture expection: ", e)

async def Run():
    while True:
      await Detect()
      now = datetime.datetime.now()
      wakeup_time = now + datetime.timedelta(seconds = 60)
      # Next wakeup time
      if now.hour < 8:
        wakeup_time = now.replace(hour = 8, minute = 0, second = 0)
      elif now.hour >= 10 and now.hour < 21:
        wakeup_time = now.replace(hour = 21, minute = 0, second = 0)
      sleep_time = (wakeup_time - now).total_seconds()
      print("Next wakeup in ", wakeup_time, "sleep seconds: ", sleep_time)
      await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(Run())


# payload = {'token': API_SERVER_VERIFY_TOKEN}
# print(requests.get(API_SERVER_URL, params=payload).text)
