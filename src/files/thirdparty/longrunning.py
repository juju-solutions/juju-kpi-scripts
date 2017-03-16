#!/usr/bin/env python3

import glob
import os
from kpi_common import get_push_gateway
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import stats


stats.logs = [
    glob.glob('/var/tmp/logs/api/1/api.jujucharms.com.log-201*'),
    glob.glob('/var/tmp/logs/api/2/api.jujucharms.com.log-201*'),
]


stats.DB_NAME = '/var/tmp/juju-models.db'


def compute_model_ages(conn, day):
    c = conn.cursor()
    sql = '''
        SELECT count(uuid), running
        FROM (
            SELECT model_hits.uuid, count(model_hits.day) as running
            FROM models, model_hits
            WHERE models.uuid = model_hits.uuid
            GROUP BY model_hits.uuid
            HAVING model_hits.day=?)
        GROUP BY running
        ORDER BY running DESC;'''
    res = c.execute(sql, [day]).fetchall()
    return res


def register_last_day_stats(registry):
    conn = stats.connect_sql()
    day = stats._get_latest_day(conn)

    # Register last days clouds
    clouds = stats.count_clouds(conn, day=day)
    for row in clouds:
        cloud_name = row[1].replace('-','_')
        cloud_num = row[0]
        print("{0}\t{1}".format(cloud_num, cloud_name))
        cloud_last_day = Gauge(
            'live_juju_cloud_{}_last_day'.format(cloud_name),
            'Cloud {} at {}'.format(cloud_name, day),
            ['name'],
            registry=registry,
        )
        cloud_last_day.labels(cloud_name).set(cloud_num)

    # Register last days cloud regions
    clouds = stats.count_cloud_regions(conn, day=day)
    cloud_name = None
    for row in clouds:
        if cloud_name != row[1]:
            print('Cloud: ', row[1])
            cloud_name = row[1].replace('-','_')

        cloud_region = row[2].replace('-','_')
        cloud_num = row[0]
        print("\t{0}\t{1}\t{2}".format(cloud_name, cloud_region, cloud_num))
        cloud_region_last_day = Gauge(
            'live_juju_cloud_region_{}_{}_last_day'.format(cloud_name, cloud_region),
            'Cloud {} on {} at {}'.format(cloud_name, cloud_region, day),
            ['name', 'region'],
            registry=registry,
        )
        cloud_region_last_day.labels(cloud_name, cloud_region).set(cloud_num)

    # Register last days versions
    versions = stats.count_versions(conn, day=day)
    for row in versions:
        version = row[1].replace('-','_').replace('.', '')
        count = row[0]
        print("{0}\t{1}".format(count, version))
        version_last_day = Gauge(
            'live_juju_version_{}_last_day'.format(version),
            'Version {} at {}'.format(version, day),
            ['version'],
            registry=registry,
        )
        version_last_day.labels(version).set(count)

    # Register last days unique models
    count = stats.count_uuids(conn, day=day)
    print("\n\n{} saw {} unique models".format(day, count))
    models_last_day = Gauge(
        'live_juju_models_last_day',
        'Models at {}'.format(day),
        registry=registry,
    )
    models_last_day.set(count)


    # Register last days model ages
    ages = compute_model_ages(conn, day=day)
    for row in ages:
        age = row[1]
        models_num = row[0]
        age_last_day = Gauge(
            'live_juju_age_{}_last_day'.format(age),
            'Models with age {} at {}'.format(age, day),
            ['age'],
            registry=registry,
        )
        age_last_day.labels(age).set(models_num)


if __name__ == "__main__":
    if not os.path.exists(stats.DB_NAME):
        stats.recreate_db()
        stats.load_logfiles()
    else:
        stats.load_logfiles()

    registry = CollectorRegistry()
    pkg = 'juju-kpi-scripts'
    name = 'juju-live-stats'

    register_last_day_stats(registry)

    gateway = get_push_gateway(pkg, name)
    push_to_gateway(gateway, job=name, registry=registry)
