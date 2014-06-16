-- Remove `CannedResponse` `type` for add-ons vs. apps (bug 1021837).

alter table cannedresponses drop column type;
