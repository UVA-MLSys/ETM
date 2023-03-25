import pandas as pd

class SnowparkRunner:
    '''
    Python class for running the Snowpark functions needed for this project.
    Invloves querying data from Snowflake tables

    Snowflake documentation: https://docs.snowflake.com/en/reference
    '''

    def __init__(self, sp_conn):
        '''
        Purpose: Creates a new SnowparkRunner instance

        INPUTS:
        sp_conn - SnowparkConnector instance
        '''
        self.sp_conn = sp_conn
    
    def query_classification_dataset(self, first_threshold):
        '''
        Purpose: Run the Snowflake query to get the classification dataset for the model

        INPUTS:
        first_threshold - int the number of minimum events used to limit the query

        OUTPUTS:
        classification_df - Pandas dataframe with the classification dataset
        '''

        classification_query = """
        WITH event_expanded AS (
            SELECT 
                e.id AS event_id
                , e.set_profile AS profile_id
                , LOWER(e.referer) AS referer
                , e.created
                -- ranking of event per visitor based on created time
                , ROW_NUMBER() OVER (PARTITION BY e.set_profile ORDER BY e.created) AS event_rank
                , p.user_id AS email
                , LOWER(c.type) AS content_type
                , c.id AS content_id
                , c.score AS content_score
            FROM event e
            LEFT JOIN content c ON CONCAT(e.source, '_', e.content_id) = c.id
            LEFT JOIN profile p ON e.set_profile = p.id
            WHERE DATE_TRUNC('year', e.day) >= DATE('2022-01-01') -- 2022 to Present
        )
        , events_with_diff AS (
            SELECT 
                *
                -- subtract created of next event in the list per each visitor
                , DATEDIFF('second', created, LEAD(created) OVER(PARTITION BY profile_id ORDER BY event_rank)) AS seconds_to_next_event
            FROM event_expanded
        )
        , idle_hours AS (
            SELECT 
                AVG(seconds_to_next_event) AS mean_time
                , 1/AVG(seconds_to_next_event) AS lam
                , (-1 * AVG(seconds_to_next_event) * LN(0.05)) / (60 * 60) AS avg_idle_hours
            FROM events_with_diff
        )
        , event_aggs AS (
            SELECT
                profile_id
                , COUNT(DISTINCT event_id) AS events
                , MAX(created) AS latest_event
            FROM events_with_diff
            GROUP BY 1
        )
        , event_aggs_first_{0} AS (
            SELECT
                e.profile_id
                , COUNT(DISTINCT CASE WHEN (e.seconds_to_next_event / (60*60)) >= i.avg_idle_hours THEN event_id END) + 1 AS cycles
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' THEN event_id END) AS article_events
                , COUNT(DISTINCT content_id) AS distinct_content
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' THEN content_id END) AS distinct_articles
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' AND referer like '%www.google.com%' THEN content_id END) AS distinct_articles_from_google
                , AVG(content_score) AS average_content_score
                , MAX(created) AS latest_event_time
                , MIN(created) AS first_event_time
                , COUNT(DISTINCT DATE_TRUNC('day', created)) AS distinct_days
            FROM events_with_diff e
            JOIN idle_hours i ON 1 = 1
            WHERE e.event_rank <= {0} -- first {0} events only
            GROUP BY 1
        )
        , time_to_{0} AS (
            SELECT
                a.profile_id
                , DATEDIFF('day', a.created, b.created) AS days_to_{0}
            FROM event_expanded a
            LEFT JOIN event_expanded b ON a.profile_id = b.profile_id AND b.event_rank = {0}
            WHERE a.event_rank = 1
        )

        SELECT
            ea.profile_id
            , CASE
                WHEN e.events >= {0} THEN 1
                ELSE 0
            END AS reached_{0}_events
            , CASE
                WHEN DATEDIFF('day', e.latest_event, CURRENT_TIMESTAMP()) <= 21 THEN 1
                ELSE 0
            END AS recent_last_event
            , ea.cycles AS event_cycles_f{0}
            , ea.distinct_articles AS distinct_articles_f{0}
            , CASE
                WHEN ea.distinct_articles > 0 THEN ea.distinct_articles_from_google / ea.distinct_articles
                ELSE 0
            END AS percent_google_articles_f{0}
            , CASE
                WHEN ea.distinct_content > 0 THEN ea.distinct_articles / ea.distinct_content
                ELSE 0
            END AS percent_article_content_f{0}
            , COALESCE(ea.average_content_score, 0) AS average_content_score_f{0}
            , ttf.days_to_{0} AS days_to_{0}_events
            , e.events
            , ea.first_event_time
            , ea.latest_event_time AS event_time_{0}
            , ea.distinct_days AS distinct_days_f{0}
        FROM event_aggs_first_{0} ea
        JOIN event_aggs e ON ea.profile_id = e.profile_id
        LEFT JOIN time_to_{0} ttf ON ea.profile_id = ttf.profile_id
        WHERE e.events >= {0}
        """.format(first_threshold)

        classification_df = self.sp_conn.query_snowpark(classification_query)

        return classification_df

    def query_clustering_dataset(self, first_threshold):
        '''
        Purpose: Run the Snowflake query to get the clustering dataset for the model

        INPUTS:
        first_threshold - int the number of minimum events used to limit the query

        OUTPUTS:
        clustering_df - Pandas dataframe with the clustering dataset
        '''

        clustering_query = """
        WITH event_expanded AS (
            SELECT 
                e.id AS event_id
                , e.set_profile AS profile_id
                , LOWER(e.referer) AS referer
                , e.created
                -- ranking of event per visitor based on created time
                , ROW_NUMBER() OVER (PARTITION BY e.set_profile ORDER BY e.created) AS event_rank
                , p.user_id AS email
                , LOWER(c.type) AS content_type
                , c.id AS content_id
                , c.score AS content_score
            FROM event e
            LEFT JOIN content c ON CONCAT(e.source, '_', e.content_id) = c.id
            LEFT JOIN profile p ON e.set_profile = p.id
            WHERE DATE_TRUNC('year', e.day) >= DATE('2022-01-01') -- 2022 to Present
        )
        , events_with_diff AS (
            SELECT 
                *
                -- subtract created of next event in the list per each visitor
                , DATEDIFF('second', created, LEAD(created) OVER(PARTITION BY profile_id ORDER BY event_rank)) AS seconds_to_next_event
            FROM event_expanded
        )
        , idle_hours AS (
            SELECT 
                AVG(seconds_to_next_event) AS mean_time
                , 1/AVG(seconds_to_next_event) AS lam
                , (-1 * AVG(seconds_to_next_event) * LN(0.05)) / (60 * 60) AS avg_idle_hours
            FROM events_with_diff
        )
        , event_aggs AS (
            SELECT
                profile_id
                , COUNT(DISTINCT event_id) AS events
                , COUNT(DISTINCT CASE WHEN (seconds_to_next_event / (60*60)) >= i.avg_idle_hours THEN event_id END) + 1 AS cycles
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' THEN event_id END) AS article_events
                , COUNT(DISTINCT content_id) AS distinct_content
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' THEN content_id END) AS distinct_articles
                , COUNT(DISTINCT CASE WHEN content_type LIKE '%article%' AND referer like '%www.google.com%' THEN content_id END) AS distinct_articles_from_google
                , AVG(content_score) AS average_content_score
                , MAX(created) AS latest_event_time
                , MIN(created) AS first_event_time
                , COUNT(DISTINCT DATE_TRUNC('day', created)) AS distinct_days
            FROM events_with_diff
            JOIN idle_hours i ON 1 = 1
            GROUP BY 1
        )
        , time_to_{0} AS (
            SELECT
                a.profile_id
                , DATEDIFF('day', a.created, b.created) AS days_to_{0}
            FROM event_expanded a
            LEFT JOIN event_expanded b ON a.profile_id = b.profile_id AND b.event_rank = {0}
            WHERE a.event_rank = 1
        )

        SELECT
            ea.profile_id
            , CASE
                WHEN ea.events >= {0} THEN 1
                ELSE 0
            END AS reached_{0}_events
            , CASE
                WHEN DATEDIFF('day', ea.latest_event_time, CURRENT_TIMESTAMP()) <= 21 THEN 1
                ELSE 0
            END AS recent_last_event
            , ea.cycles AS event_cycles_all
            , ea.distinct_articles AS distinct_articles_all
            , CASE
                WHEN ea.distinct_articles > 0 THEN ea.distinct_articles_from_google / ea.distinct_articles
                ELSE 0
            END AS percent_google_articles_all
            , CASE
                WHEN ea.distinct_content > 0 THEN ea.distinct_articles / ea.distinct_content
                ELSE 0
            END AS percent_article_content_all
            , COALESCE(ea.average_content_score, 0) AS average_content_score_all
            , ttf.days_to_{0} AS days_to_{0}_events
            , ea.events
            , ea.first_event_time
            , ea.latest_event_time
            , ea.distinct_days
        FROM event_aggs ea
        LEFT JOIN time_to_{0} ttf ON ea.profile_id = ttf.profile_id
        """.format(first_threshold)

        clustering_df = self.sp_conn.query_snowpark(clustering_query)

        return clustering_df