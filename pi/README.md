# Deleting crazy entries

Sometimes the stars align and at weird timings the reported #'s from the grip sensor get wonky. to remediate we can:

```
# Scott can do this only. Needs office internet conn
$ ssh -i ~/.ssh/is_rsa.pem scott@gripper.local
$ cd grip-tracker/pi
$ sudo docker exec -it influxdb /bin/bash
$ influx delete   --org grip   --bucket grip   --start '2025-09-11T01:00:00Z'   --stop  '2025-09-11T23:00:00Z'   --predicate '_measurement="grip_max" AND "user"="Skyler" AND "side"="right"'
```
