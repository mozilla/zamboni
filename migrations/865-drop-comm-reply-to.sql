ALTER TABLE comm_thread_notes
    DROP COLUMN `reply_to_id`,
    DROP FOREIGN KEY `reply_to_id_refs_id_df5d5709`;
