-- remove add-on-specific fields from `Contribution` model (bug 1026281)

-- `Contribution.post_data`
alter table stats_contributions drop column post_data;

-- `Contribution.charity`
alter table stats_contributions drop foreign key stats_contributions_ibfk_2;
alter table stats_contributions drop column charity_id;

alter table addons drop foreign key addons_ibfk_15;
alter table addons drop column charity_id;

drop table charities;

-- `Contribution.annoying`
-- `Contribution.is_suggested`
-- `Contribution.suggested_amount`
alter table stats_contributions drop column annoying,
                                drop column is_suggested,
                                drop column suggested_amount;
