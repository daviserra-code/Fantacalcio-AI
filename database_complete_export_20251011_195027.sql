-- PostgreSQL Database Export
-- Generated: 2025-10-11T19:50:27.800531
-- Database: Neon PostgreSQL 16.9


-- Table: flask_dance_oauth
DROP TABLE IF EXISTS flask_dance_oauth CASCADE;
CREATE TABLE flask_dance_oauth (
  user_id integer,
  browser_session_key character varying NOT NULL,
  id integer NOT NULL DEFAULT nextval('flask_dance_oauth_id_seq'::regclass),
  provider character varying(50) NOT NULL,
  created_at timestamp without time zone NOT NULL,
  token json NOT NULL
);

ALTER TABLE flask_dance_oauth ADD PRIMARY KEY (id);


-- Table: subscriptions
DROP TABLE IF EXISTS subscriptions CASCADE;
CREATE TABLE subscriptions (
  id integer NOT NULL DEFAULT nextval('subscriptions_id_seq'::regclass),
  user_id integer NOT NULL,
  stripe_subscription_id character varying(100) NOT NULL,
  status character varying(20) NOT NULL,
  current_period_start timestamp without time zone NOT NULL,
  current_period_end timestamp without time zone NOT NULL,
  created_at timestamp without time zone,
  updated_at timestamp without time zone
);

ALTER TABLE subscriptions ADD PRIMARY KEY (id);


-- Table: user_leagues
DROP TABLE IF EXISTS user_leagues CASCADE;
CREATE TABLE user_leagues (
  id integer NOT NULL DEFAULT nextval('user_leagues_id_seq'::regclass),
  user_id integer NOT NULL,
  league_name character varying(100) NOT NULL,
  league_data text,
  created_at timestamp without time zone,
  updated_at timestamp without time zone
);

ALTER TABLE user_leagues ADD PRIMARY KEY (id);


-- Table: users
DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
  id integer NOT NULL DEFAULT nextval('users_id_seq'::regclass),
  username character varying(80) NOT NULL,
  email character varying(120) NOT NULL,
  password_hash character varying(256) NOT NULL,
  first_name character varying(50),
  last_name character varying(50),
  profile_image_url character varying(255),
  pro_expires_at timestamp without time zone,
  stripe_customer_id character varying(100),
  is_active boolean,
  created_at timestamp without time zone,
  updated_at timestamp without time zone
);

ALTER TABLE users ADD PRIMARY KEY (id);

-- Data for users
INSERT INTO users (id, username, email, password_hash, first_name, last_name, profile_image_url, pro_expires_at, stripe_customer_id, is_active, created_at, updated_at) VALUES (1, 'elgreco', 'daviserra@gmail.com', 'scrypt:32768:8:1$xW5gqv4uFIIZbmWJ$b73ca82717dd8826a091d8c1739390809aa2a11ad064138cca0d512c8fc42da0a4e48b76b552d08f6a4262d043a384e101e1251dedc38bf465b1f78c032793cc', 'Davide', 'Serra', NULL, NULL, NULL, True, '2025-09-23T19:07:42.974877', '2025-09-23T19:07:42.974883');


-- Foreign Keys
ALTER TABLE flask_dance_oauth ADD CONSTRAINT flask_dance_oauth_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
ALTER TABLE user_leagues ADD CONSTRAINT user_leagues_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
