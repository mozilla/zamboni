DROP TABLE IF EXISTS waffle_flag_amo_groups;
DROP TABLE IF EXISTS waffle_flag_amo_users;
DROP TABLE IF EXISTS waffle_flag_amo;
DROP TABLE IF EXISTS waffle_sample_amo;
DROP TABLE IF EXISTS waffle_switch_amo;

DELETE FROM waffle_flag_mkt_users WHERE flag_id = (SELECT id FROM waffle_flag_mkt WHERE name='disco-pane-show-recs');
DELETE FROM waffle_flag_mkt_groups WHERE flag_id = (SELECT id FROM waffle_flag_mkt WHERE name='disco-pane-show-recs');
DELETE FROM waffle_flag_mkt WHERE name='disco-pane-show-recs';

DELETE FROM waffle_flag_mkt_users WHERE flag_id = (SELECT id FROM waffle_flag_mkt WHERE name='submit-personas');
DELETE FROM waffle_flag_mkt_groups WHERE flag_id = (SELECT id FROM waffle_flag_mkt WHERE name='submit-personas');
DELETE FROM waffle_flag_mkt WHERE name='submit-personas';

DELETE FROM waffle_sample_mkt WHERE name='disco-pane-store-collections';
