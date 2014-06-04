-- If the developer hasn't requested approval in China yet,
-- let's default to marking it as pending.

update webapps_geodata
    set region_cn_status = 2, region_cn_nominated = NOW()
    where region_cn_nominated is null;
