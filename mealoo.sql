--
-- PostgreSQL database dump
--

\restrict eImhxaDTq4BHGS04UpupIhxfhkeAEM8z1PCRi0VAS5ZcipkdJS9QhfxP9MD5WuX

-- Dumped from database version 17.10
-- Dumped by pg_dump version 17.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: auth; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA auth;


ALTER SCHEMA auth OWNER TO postgres;

--
-- Name: master; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA master;


ALTER SCHEMA master OWNER TO postgres;

--
-- Name: provider; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA provider;


ALTER SCHEMA provider OWNER TO postgres;

--
-- Name: subscription; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA subscription;


ALTER SCHEMA subscription OWNER TO postgres;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: meal_service_type; Type: TYPE; Schema: provider; Owner: postgres
--

CREATE TYPE provider.meal_service_type AS ENUM (
    'Lunch',
    'Dinner',
    'Breakfast',
    'Lunch and Dinner',
    'Lunch and Breakfast',
    'Breakfast and Dinner',
    'Lunch and Dinner and Breakfast',
    'Full Day'
);


ALTER TYPE provider.meal_service_type OWNER TO postgres;

--
-- Name: complaint_against; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.complaint_against AS ENUM (
    'vendor',
    'delivery',
    'platform'
);


ALTER TYPE public.complaint_against OWNER TO postgres;

--
-- Name: complaint_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.complaint_status AS ENUM (
    'open',
    'investigating',
    'resolved',
    'rejected'
);


ALTER TYPE public.complaint_status OWNER TO postgres;

--
-- Name: day_of_week; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.day_of_week AS ENUM (
    'mon',
    'tue',
    'wed',
    'thu',
    'fri',
    'sat',
    'sun'
);


ALTER TYPE public.day_of_week OWNER TO postgres;

--
-- Name: gender_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.gender_type AS ENUM (
    'male',
    'female',
    'other',
    'prefer_not_to_say'
);


ALTER TYPE public.gender_type OWNER TO postgres;

--
-- Name: meal_slot; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.meal_slot AS ENUM (
    'lunch',
    'dinner',
    'both'
);


ALTER TYPE public.meal_slot OWNER TO postgres;

--
-- Name: notification_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.notification_type AS ENUM (
    'order_reminder',
    'skip_reminder',
    'subscription_expiry',
    'payment_due',
    'complaint_update',
    'general'
);


ALTER TYPE public.notification_type OWNER TO postgres;

--
-- Name: order_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.order_status AS ENUM (
    'scheduled',
    'preparing',
    'out_for_delivery',
    'delivered',
    'skipped',
    'missed',
    'cancelled'
);


ALTER TYPE public.order_status OWNER TO postgres;

--
-- Name: otp_channel; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.otp_channel AS ENUM (
    'sms',
    'email'
);


ALTER TYPE public.otp_channel OWNER TO postgres;

--
-- Name: otp_purpose; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.otp_purpose AS ENUM (
    'registration',
    'login',
    'phone_change',
    'email_change'
);


ALTER TYPE public.otp_purpose OWNER TO postgres;

--
-- Name: package_category; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.package_category AS ENUM (
    'veg',
    'non_veg',
    'egg',
    'special'
);


ALTER TYPE public.package_category OWNER TO postgres;

--
-- Name: payment_method; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_method AS ENUM (
    'upi',
    'card',
    'net_banking',
    'wallet',
    'cash'
);


ALTER TYPE public.payment_method OWNER TO postgres;

--
-- Name: payment_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_status AS ENUM (
    'pending',
    'paid',
    'failed',
    'refunded'
);


ALTER TYPE public.payment_status OWNER TO postgres;

--
-- Name: subscription_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.subscription_status AS ENUM (
    'pending',
    'active',
    'paused',
    'completed',
    'cancelled'
);


ALTER TYPE public.subscription_status OWNER TO postgres;

--
-- Name: subscription_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.subscription_type AS ENUM (
    'monthly',
    'half_monthly',
    'weekly',
    'ten_day',
    'daily',
    'one_time'
);


ALTER TYPE public.subscription_type OWNER TO postgres;

--
-- Name: user_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_status AS ENUM (
    'active',
    'inactive',
    'suspended',
    'deleted'
);


ALTER TYPE public.user_status OWNER TO postgres;

--
-- Name: vendor_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.vendor_status AS ENUM (
    'active',
    'inactive',
    'suspended',
    'full',
    'deleted'
);


ALTER TYPE public.vendor_status OWNER TO postgres;

--
-- Name: wallet_txn_reason; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.wallet_txn_reason AS ENUM (
    'subscription_payment',
    'extra_order_payment',
    'skip_refund',
    'complaint_credit',
    'transfer_in',
    'transfer_out',
    'admin_adjustment'
);


ALTER TYPE public.wallet_txn_reason OWNER TO postgres;

--
-- Name: wallet_txn_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.wallet_txn_type AS ENUM (
    'credit',
    'debit'
);


ALTER TYPE public.wallet_txn_type OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: notifications; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.notifications (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    type public.notification_type NOT NULL,
    title character varying(150) NOT NULL,
    body text NOT NULL,
    data jsonb,
    is_read boolean DEFAULT false NOT NULL,
    read_at timestamp with time zone,
    sent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE auth.notifications OWNER TO postgres;

--
-- Name: otp_logs; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.otp_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    contact character varying(255) NOT NULL,
    channel public.otp_channel NOT NULL,
    purpose public.otp_purpose NOT NULL,
    otp_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    attempts smallint DEFAULT 0 NOT NULL,
    is_used boolean DEFAULT false NOT NULL,
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    hashed_password character varying(1024)
);


ALTER TABLE auth.otp_logs OWNER TO postgres;

--
-- Name: user_addresses; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.user_addresses (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    label character varying(50) DEFAULT 'Home'::character varying NOT NULL,
    address_line1 text NOT NULL,
    address_line2 text,
    landmark text,
    city character varying(100) NOT NULL,
    state character varying(100) NOT NULL,
    pin_code character varying(10) NOT NULL,
    country character varying(60) DEFAULT 'India'::character varying NOT NULL,
    latitude numeric(9,6),
    longitude numeric(10,6),
    is_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_addresses_latitude_check CHECK (((latitude >= ('-90'::integer)::numeric) AND (latitude <= (90)::numeric))),
    CONSTRAINT user_addresses_longitude_check CHECK (((longitude >= ('-180'::integer)::numeric) AND (longitude <= (180)::numeric)))
);


ALTER TABLE auth.user_addresses OWNER TO postgres;

--
-- Name: user_sessions; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.user_sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    refresh_token text NOT NULL,
    device_info jsonb,
    ip_address inet,
    last_active_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE auth.user_sessions OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.users (
    id bigint NOT NULL,
    user_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email public.citext,
    phone character varying(15),
    phone_verified boolean DEFAULT false NOT NULL,
    email_verified boolean DEFAULT false NOT NULL,
    password_hash text,
    full_name character varying(100),
    gender public.gender_type,
    date_of_birth date,
    avatar_url text,
    is_profile_completed boolean DEFAULT false NOT NULL,
    status public.user_status DEFAULT 'active'::public.user_status NOT NULL,
    referral_code character varying(12),
    referred_by uuid,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT chk_users_contact CHECK (((email IS NOT NULL) OR (phone IS NOT NULL)))
);


ALTER TABLE auth.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: auth; Owner: postgres
--

CREATE SEQUENCE auth.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE auth.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: postgres
--

ALTER SEQUENCE auth.users_id_seq OWNED BY auth.users.id;


--
-- Name: admin_users; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.admin_users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    full_name character varying(100) NOT NULL,
    email public.citext NOT NULL,
    password_hash text NOT NULL,
    role character varying(50) DEFAULT 'support'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE master.admin_users OWNER TO postgres;

--
-- Name: audit_logs; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
)
PARTITION BY RANGE (created_at);


ALTER TABLE master.audit_logs OWNER TO postgres;

--
-- Name: audit_logs_2025_01; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_01 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_01 OWNER TO postgres;

--
-- Name: audit_logs_2025_02; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_02 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_02 OWNER TO postgres;

--
-- Name: audit_logs_2025_03; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_03 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_03 OWNER TO postgres;

--
-- Name: audit_logs_2025_04; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_04 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_04 OWNER TO postgres;

--
-- Name: audit_logs_2025_05; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_05 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_05 OWNER TO postgres;

--
-- Name: audit_logs_2025_06; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_06 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_06 OWNER TO postgres;

--
-- Name: audit_logs_2025_07; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_07 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_07 OWNER TO postgres;

--
-- Name: audit_logs_2025_08; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_08 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_08 OWNER TO postgres;

--
-- Name: audit_logs_2025_09; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_09 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_09 OWNER TO postgres;

--
-- Name: audit_logs_2025_10; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_10 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_10 OWNER TO postgres;

--
-- Name: audit_logs_2025_11; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_11 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_11 OWNER TO postgres;

--
-- Name: audit_logs_2025_12; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2025_12 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2025_12 OWNER TO postgres;

--
-- Name: audit_logs_2026_01; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_01 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_01 OWNER TO postgres;

--
-- Name: audit_logs_2026_02; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_02 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_02 OWNER TO postgres;

--
-- Name: audit_logs_2026_03; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_03 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_03 OWNER TO postgres;

--
-- Name: audit_logs_2026_04; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_04 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_04 OWNER TO postgres;

--
-- Name: audit_logs_2026_05; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_05 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_05 OWNER TO postgres;

--
-- Name: audit_logs_2026_06; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_06 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_06 OWNER TO postgres;

--
-- Name: audit_logs_2026_07; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_07 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_07 OWNER TO postgres;

--
-- Name: audit_logs_2026_08; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_08 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_08 OWNER TO postgres;

--
-- Name: audit_logs_2026_09; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_09 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_09 OWNER TO postgres;

--
-- Name: audit_logs_2026_10; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_10 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_10 OWNER TO postgres;

--
-- Name: audit_logs_2026_11; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_11 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_11 OWNER TO postgres;

--
-- Name: audit_logs_2026_12; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.audit_logs_2026_12 (
    id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id uuid NOT NULL,
    operation character(1) NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_by uuid,
    changed_by_type character varying(10),
    ip_address inet,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_operation_check CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))
);


ALTER TABLE master.audit_logs_2026_12 OWNER TO postgres;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

ALTER TABLE master.audit_logs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME master.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: menu_categories; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.menu_categories (
    id bigint NOT NULL,
    category_id uuid NOT NULL,
    category_name character varying(150) NOT NULL,
    category_slug character varying(150),
    description text,
    display_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE master.menu_categories OWNER TO postgres;

--
-- Name: menu_categories_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.menu_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.menu_categories_id_seq OWNER TO postgres;

--
-- Name: menu_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.menu_categories_id_seq OWNED BY master.menu_categories.id;


--
-- Name: menu_package_images; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.menu_package_images (
    id bigint NOT NULL,
    image_id uuid NOT NULL,
    package_id uuid NOT NULL,
    image_url text NOT NULL,
    is_primary boolean DEFAULT false,
    display_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE master.menu_package_images OWNER TO postgres;

--
-- Name: menu_package_images_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.menu_package_images_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.menu_package_images_id_seq OWNER TO postgres;

--
-- Name: menu_package_images_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.menu_package_images_id_seq OWNED BY master.menu_package_images.id;


--
-- Name: menu_package_items; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.menu_package_items (
    id bigint NOT NULL,
    item_id uuid NOT NULL,
    package_id uuid NOT NULL,
    item_name character varying(255) NOT NULL,
    quantity character varying(100),
    item_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE master.menu_package_items OWNER TO postgres;

--
-- Name: menu_package_items_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.menu_package_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.menu_package_items_id_seq OWNER TO postgres;

--
-- Name: menu_package_items_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.menu_package_items_id_seq OWNED BY master.menu_package_items.id;


--
-- Name: menu_packages; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.menu_packages (
    id bigint NOT NULL,
    package_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    category_id uuid NOT NULL,
    package_name character varying(255) NOT NULL,
    short_description character varying(500),
    description text,
    meal_type character varying(50),
    food_type character varying(50),
    price numeric(10,2) NOT NULL,
    discounted_price numeric(10,2),
    is_subscription_available boolean DEFAULT false,
    subscription_price numeric(10,2),
    duration_type character varying(50),
    calories integer,
    protein_grams integer,
    carbs_grams integer,
    fats_grams integer,
    serving_persons integer,
    spice_level character varying(20),
    preparation_time integer,
    is_available boolean DEFAULT true,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE master.menu_packages OWNER TO postgres;

--
-- Name: menu_packages_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.menu_packages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.menu_packages_id_seq OWNER TO postgres;

--
-- Name: menu_packages_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.menu_packages_id_seq OWNED BY master.menu_packages.id;


--
-- Name: service_unavailable_logs; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.service_unavailable_logs (
    id bigint NOT NULL,
    log_id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_id uuid,
    pincode integer NOT NULL,
    house_no character varying(100),
    address text,
    landmark character varying(255),
    city character varying(100),
    state character varying(100),
    requested_from character varying(50),
    remarks text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE master.service_unavailable_logs OWNER TO postgres;

--
-- Name: service_unavailable_logs_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.service_unavailable_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.service_unavailable_logs_id_seq OWNER TO postgres;

--
-- Name: service_unavailable_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.service_unavailable_logs_id_seq OWNED BY master.service_unavailable_logs.id;


--
-- Name: serviceable_pincodes; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.serviceable_pincodes (
    pincode_id bigint NOT NULL,
    pincode integer NOT NULL,
    city character varying(100) NOT NULL,
    state character varying(100) NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE master.serviceable_pincodes OWNER TO postgres;

--
-- Name: serviceable_pincodes_pincode_id_seq; Type: SEQUENCE; Schema: master; Owner: postgres
--

CREATE SEQUENCE master.serviceable_pincodes_pincode_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE master.serviceable_pincodes_pincode_id_seq OWNER TO postgres;

--
-- Name: serviceable_pincodes_pincode_id_seq; Type: SEQUENCE OWNED BY; Schema: master; Owner: postgres
--

ALTER SEQUENCE master.serviceable_pincodes_pincode_id_seq OWNED BY master.serviceable_pincodes.pincode_id;


--
-- Name: subscription_plans; Type: TABLE; Schema: master; Owner: postgres
--

CREATE TABLE master.subscription_plans (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    subscription_type public.subscription_type NOT NULL,
    meal_slot public.meal_slot NOT NULL,
    duration_days smallint NOT NULL,
    free_skips smallint DEFAULT 6 NOT NULL,
    discount_percent numeric(5,2) DEFAULT 0.00 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE master.subscription_plans OWNER TO postgres;

--
-- Name: complaints; Type: TABLE; Schema: provider; Owner: postgres
--

CREATE TABLE provider.complaints (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    order_id uuid,
    against public.complaint_against DEFAULT 'vendor'::public.complaint_against NOT NULL,
    status public.complaint_status DEFAULT 'open'::public.complaint_status NOT NULL,
    subject character varying(255) NOT NULL,
    description text NOT NULL,
    evidence_urls text[],
    admin_notes text,
    resolved_by uuid,
    resolution text,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE provider.complaints OWNER TO postgres;

--
-- Name: otp_logs; Type: TABLE; Schema: provider; Owner: postgres
--

CREATE TABLE provider.otp_logs (
    otp_log_id uuid NOT NULL,
    mobile_number character varying(32) NOT NULL,
    otp character varying(16) NOT NULL,
    expires_at timestamp with time zone,
    is_verified boolean,
    attempts integer,
    created_at timestamp with time zone,
    hashed_password character varying(255)
);


ALTER TABLE provider.otp_logs OWNER TO postgres;

--
-- Name: provider_selected_packages; Type: TABLE; Schema: provider; Owner: postgres
--

CREATE TABLE provider.provider_selected_packages (
    id bigint NOT NULL,
    selection_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    package_id uuid NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE provider.provider_selected_packages OWNER TO postgres;

--
-- Name: provider_selected_packages_id_seq; Type: SEQUENCE; Schema: provider; Owner: postgres
--

CREATE SEQUENCE provider.provider_selected_packages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE provider.provider_selected_packages_id_seq OWNER TO postgres;

--
-- Name: provider_selected_packages_id_seq; Type: SEQUENCE OWNED BY; Schema: provider; Owner: postgres
--

ALTER SEQUENCE provider.provider_selected_packages_id_seq OWNED BY provider.provider_selected_packages.id;


--
-- Name: providers; Type: TABLE; Schema: provider; Owner: postgres
--

CREATE TABLE provider.providers (
    id bigint NOT NULL,
    mobile_number character varying NOT NULL,
    is_mobile_verified boolean DEFAULT false NOT NULL,
    is_profile_completed boolean DEFAULT false NOT NULL,
    full_name character varying(128),
    business_name character varying(256),
    city character varying(128),
    area character varying(258),
    address text,
    kitchen_type character varying(128),
    profile_image text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    provider_id uuid NOT NULL,
    hashed_password character varying(255) NOT NULL,
    pincode integer,
    landmark character varying(128),
    state character varying(64),
    house_no character varying(64),
    meal_service_type provider.meal_service_type
);


ALTER TABLE provider.providers OWNER TO postgres;

--
-- Name: providers_id_seq; Type: SEQUENCE; Schema: provider; Owner: postgres
--

ALTER TABLE provider.providers ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME provider.providers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: reviews; Type: TABLE; Schema: provider; Owner: postgres
--

CREATE TABLE provider.reviews (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    order_id uuid,
    package_id uuid NOT NULL,
    vendor_rating smallint,
    package_rating smallint,
    review_text text,
    review_date date DEFAULT CURRENT_DATE NOT NULL,
    is_visible boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pkg_rating2 CHECK (((package_rating >= 1) AND (package_rating <= 5))),
    CONSTRAINT chk_vendor_rating CHECK (((vendor_rating >= 1) AND (vendor_rating <= 5)))
);


ALTER TABLE provider.reviews OWNER TO postgres;

--
-- Name: extra_orders; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.extra_orders (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    address_id uuid NOT NULL,
    package_id uuid NOT NULL,
    quantity smallint DEFAULT 1 NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    total_price numeric(10,2) NOT NULL,
    delivery_date date NOT NULL,
    meal_slot public.meal_slot NOT NULL,
    status public.order_status DEFAULT 'scheduled'::public.order_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_extra_qty CHECK ((quantity > 0))
);


ALTER TABLE subscription.extra_orders OWNER TO postgres;

--
-- Name: orders; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.orders (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    subscription_id uuid NOT NULL,
    user_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    delivery_address_id uuid NOT NULL,
    order_date date NOT NULL,
    meal_slot public.meal_slot NOT NULL,
    status public.order_status DEFAULT 'scheduled'::public.order_status NOT NULL,
    is_free_skip boolean DEFAULT false NOT NULL,
    skip_requested_at timestamp with time zone,
    skip_deadline timestamp with time zone NOT NULL,
    delivered_at timestamp with time zone,
    delivery_notes text,
    otp_for_delivery character varying(6),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE subscription.orders OWNER TO postgres;

--
-- Name: payments; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.payments (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    subscription_id uuid,
    user_id uuid NOT NULL,
    extra_order_id uuid,
    amount numeric(10,2) NOT NULL,
    currency character(3) DEFAULT 'INR'::bpchar NOT NULL,
    method public.payment_method NOT NULL,
    status public.payment_status DEFAULT 'pending'::public.payment_status NOT NULL,
    gateway character varying(50),
    gateway_order_id text,
    gateway_txn_id text,
    gateway_response jsonb,
    paid_at timestamp with time zone,
    refunded_at timestamp with time zone,
    refund_amount numeric(10,2),
    failure_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_payment_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT chk_payment_ref CHECK ((((subscription_id IS NOT NULL) AND (extra_order_id IS NULL)) OR ((subscription_id IS NULL) AND (extra_order_id IS NOT NULL))))
);


ALTER TABLE subscription.payments OWNER TO postgres;

--
-- Name: subscription_packages; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.subscription_packages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    subscription_id uuid NOT NULL,
    package_id uuid NOT NULL,
    quantity smallint DEFAULT 1 NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_sub_pkg_qty CHECK ((quantity > 0))
);


ALTER TABLE subscription.subscription_packages OWNER TO postgres;

--
-- Name: subscriptions; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.subscriptions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    user_address_id uuid NOT NULL,
    status public.subscription_status DEFAULT 'pending'::public.subscription_status NOT NULL,
    meal_slot public.meal_slot NOT NULL,
    subscription_type public.subscription_type NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    free_skips_total smallint DEFAULT 6 NOT NULL,
    free_skips_used smallint DEFAULT 0 NOT NULL,
    total_amount numeric(10,2) NOT NULL,
    discount_amount numeric(10,2) DEFAULT 0.00 NOT NULL,
    final_amount numeric(10,2) NOT NULL,
    notes text,
    cancelled_at timestamp with time zone,
    cancel_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_sub_amount CHECK ((final_amount > (0)::numeric)),
    CONSTRAINT chk_sub_dates CHECK ((end_date > start_date)),
    CONSTRAINT chk_sub_skips CHECK ((free_skips_used <= free_skips_total))
);


ALTER TABLE subscription.subscriptions OWNER TO postgres;

--
-- Name: wallet_transactions; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.wallet_transactions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    wallet_id uuid NOT NULL,
    user_id uuid NOT NULL,
    type public.wallet_txn_type NOT NULL,
    reason public.wallet_txn_reason NOT NULL,
    amount numeric(10,2) NOT NULL,
    balance_before numeric(10,2) NOT NULL,
    balance_after numeric(10,2) NOT NULL,
    reference_id uuid,
    reference_type character varying(50),
    description text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_wtxn_amount CHECK ((amount > (0)::numeric))
);


ALTER TABLE subscription.wallet_transactions OWNER TO postgres;

--
-- Name: wallets; Type: TABLE; Schema: subscription; Owner: postgres
--

CREATE TABLE subscription.wallets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    balance numeric(10,2) DEFAULT 0.00 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_wallet_balance CHECK ((balance >= (0)::numeric))
);


ALTER TABLE subscription.wallets OWNER TO postgres;

--
-- Name: audit_logs_2025_01; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_01 FOR VALUES FROM ('2025-01-01 00:00:00+05:30') TO ('2025-02-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_02; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_02 FOR VALUES FROM ('2025-02-01 00:00:00+05:30') TO ('2025-03-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_03; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_03 FOR VALUES FROM ('2025-03-01 00:00:00+05:30') TO ('2025-04-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_04; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_04 FOR VALUES FROM ('2025-04-01 00:00:00+05:30') TO ('2025-05-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_05; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_05 FOR VALUES FROM ('2025-05-01 00:00:00+05:30') TO ('2025-06-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_06; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_06 FOR VALUES FROM ('2025-06-01 00:00:00+05:30') TO ('2025-07-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_07; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_07 FOR VALUES FROM ('2025-07-01 00:00:00+05:30') TO ('2025-08-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_08; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_08 FOR VALUES FROM ('2025-08-01 00:00:00+05:30') TO ('2025-09-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_09; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_09 FOR VALUES FROM ('2025-09-01 00:00:00+05:30') TO ('2025-10-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_10; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_10 FOR VALUES FROM ('2025-10-01 00:00:00+05:30') TO ('2025-11-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_11; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_11 FOR VALUES FROM ('2025-11-01 00:00:00+05:30') TO ('2025-12-01 00:00:00+05:30');


--
-- Name: audit_logs_2025_12; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2025_12 FOR VALUES FROM ('2025-12-01 00:00:00+05:30') TO ('2026-01-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_01; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_01 FOR VALUES FROM ('2026-01-01 00:00:00+05:30') TO ('2026-02-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_02; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_02 FOR VALUES FROM ('2026-02-01 00:00:00+05:30') TO ('2026-03-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_03; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_03 FOR VALUES FROM ('2026-03-01 00:00:00+05:30') TO ('2026-04-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_04; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_04 FOR VALUES FROM ('2026-04-01 00:00:00+05:30') TO ('2026-05-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_05; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_05 FOR VALUES FROM ('2026-05-01 00:00:00+05:30') TO ('2026-06-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_06; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_06 FOR VALUES FROM ('2026-06-01 00:00:00+05:30') TO ('2026-07-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_07; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_07 FOR VALUES FROM ('2026-07-01 00:00:00+05:30') TO ('2026-08-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_08; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_08 FOR VALUES FROM ('2026-08-01 00:00:00+05:30') TO ('2026-09-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_09; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_09 FOR VALUES FROM ('2026-09-01 00:00:00+05:30') TO ('2026-10-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_10; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_10 FOR VALUES FROM ('2026-10-01 00:00:00+05:30') TO ('2026-11-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_11; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_11 FOR VALUES FROM ('2026-11-01 00:00:00+05:30') TO ('2026-12-01 00:00:00+05:30');


--
-- Name: audit_logs_2026_12; Type: TABLE ATTACH; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.audit_logs ATTACH PARTITION master.audit_logs_2026_12 FOR VALUES FROM ('2026-12-01 00:00:00+05:30') TO ('2027-01-01 00:00:00+05:30');


--
-- Name: users id; Type: DEFAULT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users ALTER COLUMN id SET DEFAULT nextval('auth.users_id_seq'::regclass);


--
-- Name: menu_categories id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_categories ALTER COLUMN id SET DEFAULT nextval('master.menu_categories_id_seq'::regclass);


--
-- Name: menu_package_images id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_images ALTER COLUMN id SET DEFAULT nextval('master.menu_package_images_id_seq'::regclass);


--
-- Name: menu_package_items id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_items ALTER COLUMN id SET DEFAULT nextval('master.menu_package_items_id_seq'::regclass);


--
-- Name: menu_packages id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_packages ALTER COLUMN id SET DEFAULT nextval('master.menu_packages_id_seq'::regclass);


--
-- Name: service_unavailable_logs id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.service_unavailable_logs ALTER COLUMN id SET DEFAULT nextval('master.service_unavailable_logs_id_seq'::regclass);


--
-- Name: serviceable_pincodes pincode_id; Type: DEFAULT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.serviceable_pincodes ALTER COLUMN pincode_id SET DEFAULT nextval('master.serviceable_pincodes_pincode_id_seq'::regclass);


--
-- Name: provider_selected_packages id; Type: DEFAULT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.provider_selected_packages ALTER COLUMN id SET DEFAULT nextval('provider.provider_selected_packages_id_seq'::regclass);


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.notifications (id, user_id, type, title, body, data, is_read, read_at, sent_at, created_at) FROM stdin;
\.


--
-- Data for Name: otp_logs; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.otp_logs (id, contact, channel, purpose, otp_hash, expires_at, verified_at, attempts, is_used, ip_address, created_at, hashed_password) FROM stdin;
2051a207-4a63-4ccc-8a84-96d3c78f9cb8	6264677824	sms	registration	$2b$12$FEY11675QMAU2MSBr3kMwOGHI.D24zJh9Os0JjjyrcVcmgEQ1FDuq	2026-06-02 22:42:22.96519+05:30	2026-06-02 22:29:50.467319+05:30	0	t	\N	2026-06-02 22:27:22.965747+05:30	$2b$12$qPwvMEmuBPyxaapUV/m3qubWsT3RcraZuqK5HwodUC4fABwehdk6i
\.


--
-- Data for Name: user_addresses; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.user_addresses (id, user_id, label, address_line1, address_line2, landmark, city, state, pin_code, country, latitude, longitude, is_default, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_sessions; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.user_sessions (id, user_id, refresh_token, device_info, ip_address, last_active_at, expires_at, revoked_at, created_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.users (id, user_id, email, phone, phone_verified, email_verified, password_hash, full_name, gender, date_of_birth, avatar_url, is_profile_completed, status, referral_code, referred_by, last_login_at, created_at, updated_at, deleted_at) FROM stdin;
1	58365523-6517-4513-9b39-108283d46a2c	string	6264677824	t	t	$2b$12$qPwvMEmuBPyxaapUV/m3qubWsT3RcraZuqK5HwodUC4fABwehdk6i	\N	\N	\N	\N	f	active	\N	\N	2026-06-02 22:31:59.537662+05:30	2026-06-02 22:29:50.536806+05:30	2026-06-02 22:31:59.537662+05:30	\N
\.


--
-- Data for Name: admin_users; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.admin_users (id, full_name, email, password_hash, role, is_active, last_login_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_01; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_01 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_02; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_02 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_03; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_03 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_04; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_04 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_05; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_05 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_06; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_06 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_07; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_07 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_08; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_08 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_09; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_09 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_10; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_10 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_11; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_11 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2025_12; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2025_12 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_01; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_01 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_02; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_02 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_03; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_03 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_04; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_04 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_05; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_05 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_06; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_06 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_07; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_07 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_08; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_08 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_09; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_09 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_10; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_10 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_11; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_11 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: audit_logs_2026_12; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.audit_logs_2026_12 (id, table_name, record_id, operation, old_data, new_data, changed_by, changed_by_type, ip_address, created_at) FROM stdin;
\.


--
-- Data for Name: menu_categories; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.menu_categories (id, category_id, category_name, category_slug, description, display_order, is_active, created_at, updated_at) FROM stdin;
1	82a8bb0e-e01d-49f1-b23b-9224e383e045	Homemade Meal Packages	homemade-meal-packages	Daily homemade style meals and thalis	1	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
2	03c44b8d-2622-4c52-a9de-648169f9e2b6	Jain Food Packages	jain-food-packages	Pure Jain meals without onion and garlic	2	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
3	89c0d240-b293-4123-b063-084cf77a7000	High Protein Meal Packages	high-protein-meal-packages	Protein rich meals for gym and fitness	3	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
4	be210e5f-d05a-4727-b620-9cf5cd365993	No Onion Garlic Packages	no-onion-garlic-packages	Satvik meals prepared without onion and garlic	4	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
5	0b9746b2-1727-466b-a098-a4f6d994e533	Daily Changing Satvik Menu	daily-changing-satvik-menu	Rotational satvik meal packages	5	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
6	8563942e-9490-401e-be6e-da07059edb0a	Doctor/Diet-Based Meals	doctor-diet-based-meals	Customized meals based on diet and health plans	6	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
7	0ecd3784-8a25-4d35-bd58-7015e28d0eca	Pure Veg Packages	pure-veg-packages	Pure vegetarian meal packages	7	t	2026-05-22 16:10:40.182843+05:30	2026-05-22 16:10:40.182843+05:30
\.


--
-- Data for Name: menu_package_images; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.menu_package_images (id, image_id, package_id, image_url, is_primary, display_order, created_at) FROM stdin;
1	150db3a9-03af-4e16-94b5-0a7fab5bd6ad	a0925512-8007-4554-8c1d-b01eae58edc9	uploads/package_images/b1e1a280-c5f5-4556-9954-4a374986b55c.png	t	1	2026-05-28 00:32:02.018556+05:30
2	a1786d0a-68ea-4edc-bd04-4b5f76d0825b	a0925512-8007-4554-8c1d-b01eae58edc9	uploads/package_images/b6cff593-91b2-4dbe-ac28-196974bacd68.png	f	1	2026-05-28 00:36:55.866692+05:30
\.


--
-- Data for Name: menu_package_items; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.menu_package_items (id, item_id, package_id, item_name, quantity, item_order, created_at) FROM stdin;
1	2345b346-9223-4ddd-b772-b2e1e266ae66	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	Roti	4	0	2026-05-22 16:47:03.213822+05:30
2	7bc0be81-f50f-477e-8e67-b83f755a43af	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	Seasional Sabzi	1	0	2026-05-22 16:47:03.213822+05:30
3	c912b911-08de-4282-97e2-e2b8e0bba197	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	Rice	1	0	2026-05-22 16:47:03.213822+05:30
4	d7581b8f-8a03-4585-b7a4-fb85d7eaf4ac	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	Dal	1	0	2026-05-22 16:47:03.213822+05:30
5	8e94aee3-895a-477f-a5eb-398c1bae2c6a	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	Salad	1	0	2026-05-22 16:47:03.213822+05:30
6	c968ee15-be4e-45d6-be12-0161473a35e3	a0925512-8007-4554-8c1d-b01eae58edc9	Jain sabzi	1	0	2026-05-27 23:10:28.442869+05:30
7	f55c4a2a-87e4-406f-87d8-c914fd3d54e9	a0925512-8007-4554-8c1d-b01eae58edc9	Roti	4	0	2026-05-27 23:10:28.442869+05:30
8	5793bc11-9b32-4228-ba21-33dc63628ba9	a0925512-8007-4554-8c1d-b01eae58edc9	Dal	1	0	2026-05-27 23:10:28.442869+05:30
9	78e25250-2d21-4c4e-ab06-58f12ed794f9	a0925512-8007-4554-8c1d-b01eae58edc9	Rice	1	0	2026-05-27 23:10:28.442869+05:30
10	c375499b-e388-48c4-84dc-010a09a439a4	a0925512-8007-4554-8c1d-b01eae58edc9	Salad	2	6	2026-05-27 23:56:11.862545+05:30
11	0582f3a0-ee39-472c-a463-a90563bfabde	339f9436-9e4a-46fd-8804-1db7e16bc813	p1 item	20	0	2026-06-02 23:10:20.994834+05:30
12	651e3e31-e43f-444a-b5db-fca70ddebe9b	493264e4-44a9-4833-a583-984490c199e9	p2 item	10	0	2026-06-02 23:11:03.987861+05:30
\.


--
-- Data for Name: menu_packages; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.menu_packages (id, package_id, provider_id, category_id, package_name, short_description, description, meal_type, food_type, price, discounted_price, is_subscription_available, subscription_price, duration_type, calories, protein_grams, carbs_grams, fats_grams, serving_persons, spice_level, preparation_time, is_available, is_active, created_at, updated_at) FROM stdin;
1	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	b28d33e2-831b-44b1-a8b9-e93aa570fcaa	82a8bb0e-e01d-49f1-b23b-9224e383e045	Homemade Basic Thali	Simple Thali that having 4 roti, 1 Seasonal Sabzi, dal, rice and salad	Simple Thali that having 4 roti, 1 Seasonal Sabzi, dal, rice and salad	Lunch	Veg	85.00	5.00	t	100.00	\N	\N	\N	\N	\N	\N	\N	\N	t	t	2026-05-22 16:47:03.213822+05:30	2026-05-22 16:47:03.213822+05:30
2	a0925512-8007-4554-8c1d-b01eae58edc9	b28d33e2-831b-44b1-a8b9-e93aa570fcaa	03c44b8d-2622-4c52-a9de-648169f9e2b6	Jain Food Packages	jain khana without onion and garlic	jain khana without onion and garlic 3 roti 	dinner	Veg	100.00	4.00	t	100.00	\N	\N	\N	\N	\N	\N	\N	\N	t	t	2026-05-27 23:10:28.442869+05:30	2026-05-27 23:20:14.650255+05:30
3	339f9436-9e4a-46fd-8804-1db7e16bc813	8b02bdd2-d010-43cf-a579-e37c1a3ce8c9	82a8bb0e-e01d-49f1-b23b-9224e383e045	P1	dall rice sabji	this i sp1	veg	veg	20000.00	100.00	t	1000.00	\N	\N	\N	\N	\N	\N	\N	\N	t	t	2026-06-02 23:10:20.994834+05:30	2026-06-02 23:10:20.994834+05:30
4	493264e4-44a9-4833-a583-984490c199e9	8b02bdd2-d010-43cf-a579-e37c1a3ce8c9	82a8bb0e-e01d-49f1-b23b-9224e383e045	P2	dall rice sabji	this i sp1	veg	veg	30000.00	300.00	t	1500.00	\N	\N	\N	\N	\N	\N	\N	\N	t	t	2026-06-02 23:11:03.987861+05:30	2026-06-02 23:11:03.987861+05:30
\.


--
-- Data for Name: service_unavailable_logs; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.service_unavailable_logs (id, log_id, provider_id, pincode, house_no, address, landmark, city, state, requested_from, remarks, created_at) FROM stdin;
1	f4fb2005-9dec-4c49-8abe-fd6a7a2e5c1d	b28d33e2-831b-44b1-a8b9-e93aa570fcaa	110092	D405	D405 west vinod nager	Shriram Chock	Mandaveli	Delhi	provider_app	Service not available	2026-05-28 22:25:42.53797+05:30
\.


--
-- Data for Name: serviceable_pincodes; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.serviceable_pincodes (pincode_id, pincode, city, state, is_active, created_at) FROM stdin;
1	110001	Delhi	Delhi	t	2026-05-27 11:20:42.792543
2	110002	Delhi	Delhi	t	2026-05-27 11:20:42.792543
3	121001	Faridabad	Haryana	t	2026-05-27 11:20:42.792543
\.


--
-- Data for Name: subscription_plans; Type: TABLE DATA; Schema: master; Owner: postgres
--

COPY master.subscription_plans (id, subscription_type, meal_slot, duration_days, free_skips, discount_percent, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: complaints; Type: TABLE DATA; Schema: provider; Owner: postgres
--

COPY provider.complaints (id, user_id, subscription_id, vendor_id, order_id, against, status, subject, description, evidence_urls, admin_notes, resolved_by, resolution, resolved_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: otp_logs; Type: TABLE DATA; Schema: provider; Owner: postgres
--

COPY provider.otp_logs (otp_log_id, mobile_number, otp, expires_at, is_verified, attempts, created_at, hashed_password) FROM stdin;
23a8ea45-a553-4c6e-93bd-55123583ff85	7999411794	825573	2026-05-19 08:23:25.137911+05:30	f	0	2026-05-19 08:18:46.42339+05:30	\N
24db31ae-82fe-4dca-bffb-2fe54a3c5876	7999411794	432273	2026-05-19 14:08:44.897203+05:30	f	0	2026-05-19 08:24:06.12962+05:30	\N
fa859cb4-03b5-4720-b106-951992e74651	7999411794	473390	2026-05-19 14:30:30.124778+05:30	f	0	2026-05-19 08:45:30.126695+05:30	\N
bc399d61-4ea6-4020-a640-602d3ee39906	7999411794	967003	2026-05-19 14:30:31.844557+05:30	f	0	2026-05-19 08:45:31.844557+05:30	\N
993fc15c-0a1f-452b-8fef-48508ec2d9c9	7999411794	860264	2026-05-19 14:30:34.719491+05:30	t	2	2026-05-19 08:45:34.720608+05:30	\N
d8d41b96-9885-477d-aedc-6d1d685bb7a7	7999411794	252095	2026-05-19 15:01:11.072799+05:30	t	0	2026-05-19 09:16:32.347878+05:30	\N
45ddcbf6-e67f-445d-88be-d2860820581d	7999411794	836877	2026-05-19 16:52:08.696949+05:30	t	0	2026-05-19 11:07:29.998808+05:30	$2b$12$Q6MuE0GGLNTMsRMpgAmhDuLKXOtyGJDaPY8jEB5/9eqZf5.uEkyNK
ce144036-dfb3-45c5-9b10-81bb20752d0e	7999411794	849741	2026-05-19 16:54:30.049387+05:30	t	0	2026-05-19 11:09:30.049387+05:30	$2b$12$EGwpugJQL4UGMp9S..Fecu1FOs02hwsV6Ln/IztbrCpfDuBSR9Rhy
5fa914ab-8f65-4e71-ae18-7637760e14e0	7999411794	231088	2026-05-19 16:57:22.122185+05:30	t	0	2026-05-19 11:12:22.122185+05:30	$2b$12$VgjJf7ggbzX9n8ml1dcaHO9RYbHGYZtBiDqTLeX.q2i6Nya.qleTS
e2eec8c6-5613-4de3-a569-89fa41764ccc	6264677824	182620	2026-05-21 12:13:32.184725+05:30	t	0	2026-05-21 06:28:53.469746+05:30	$2b$12$nYHiB/pjPbtU02zxlhc4LOVuchO.eAiVephk9SfG61IbIutJzW78S
6dbd0b43-506c-4df1-a99c-29805c93a5be	6264677824	662431	2026-05-21 12:14:51.836093+05:30	t	0	2026-05-21 06:29:51.837074+05:30	$2b$12$LhsO1mFl6yWa2IbB6wyb3.DJ6B4qB2hGRYMqFmAIXafvdbnDnUu62
36105b4a-5b51-4bac-8cb7-07f985c7f26d	6264677824	283562	2026-05-21 12:16:38.349438+05:30	t	0	2026-05-21 06:31:38.35044+05:30	$2b$12$6KmiTddz923RANsepYqfOuoUIwl.ul9qygEWIVMeEUwPiYdl.OB2q
8a4843a3-cc03-4e27-80d1-b5208bbfe303	8340243430	875845	2026-06-02 23:21:48.178426+05:30	t	0	2026-06-02 17:36:48.180927+05:30	$2b$12$YU14Npdklj2m2kpMRX.zpuSWE8KcVDsSm9JIbZz37VfYHf9acmFvW
\.


--
-- Data for Name: provider_selected_packages; Type: TABLE DATA; Schema: provider; Owner: postgres
--

COPY provider.provider_selected_packages (id, selection_id, provider_id, package_id, is_active, created_at) FROM stdin;
1	d597499e-300a-4507-b467-583e886070ad	b28d33e2-831b-44b1-a8b9-e93aa570fcaa	b94edb32-55f7-43f1-bfd0-f64b0525a7e8	t	2026-06-01 11:31:41.402673
2	8f1cea0d-de2d-4086-a949-866ada02bd96	8b02bdd2-d010-43cf-a579-e37c1a3ce8c9	493264e4-44a9-4833-a583-984490c199e9	t	2026-06-02 23:14:45.278344
\.


--
-- Data for Name: providers; Type: TABLE DATA; Schema: provider; Owner: postgres
--

COPY provider.providers (id, mobile_number, is_mobile_verified, is_profile_completed, full_name, business_name, city, area, address, kitchen_type, profile_image, created_at, updated_at, provider_id, hashed_password, pincode, landmark, state, house_no, meal_service_type) FROM stdin;
2	6264677824	t	t	Shlok Rajput	Rajput restorent	delhi	Nirman Vihar	504, block C nirman vihar east delhi	veg	uploads/providers/profile/d0964434-5467-4228-a18b-5936243379fc.jpg	2026-05-21 11:59:37.769159+05:30	2026-05-22 12:03:39.464455+05:30	78ccb795-8af5-4735-b128-3b389939a813	$2b$12$6KmiTddz923RANsepYqfOuoUIwl.ul9qygEWIVMeEUwPiYdl.OB2q	110092	near sanatan dharm mandir	Delhi	504	\N
1	7999411794	t	t	Indar Rajput	Rajput Resturent	Delhi	Mandaveli	D404 West vinod nager Delhi	Veg	\N	2026-05-19 16:42:33.571203+05:30	2026-05-29 17:26:45.288275+05:30	b28d33e2-831b-44b1-a8b9-e93aa570fcaa	$2b$12$VgjJf7ggbzX9n8ml1dcaHO9RYbHGYZtBiDqTLeX.q2i6Nya.qleTS	110002	Shriram Chouk	Delhi	D404	Breakfast
3	8340243430	t	f	\N	\N	\N	\N	\N	\N	\N	2026-06-02 23:07:18.326745+05:30	2026-06-02 23:07:18.326745+05:30	8b02bdd2-d010-43cf-a579-e37c1a3ce8c9	$2b$12$YU14Npdklj2m2kpMRX.zpuSWE8KcVDsSm9JIbZz37VfYHf9acmFvW	\N	\N	\N	\N	\N
\.


--
-- Data for Name: reviews; Type: TABLE DATA; Schema: provider; Owner: postgres
--

COPY provider.reviews (id, user_id, subscription_id, vendor_id, order_id, package_id, vendor_rating, package_rating, review_text, review_date, is_visible, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: extra_orders; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.extra_orders (id, user_id, vendor_id, address_id, package_id, quantity, unit_price, total_price, delivery_date, meal_slot, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: orders; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.orders (id, subscription_id, user_id, vendor_id, delivery_address_id, order_date, meal_slot, status, is_free_skip, skip_requested_at, skip_deadline, delivered_at, delivery_notes, otp_for_delivery, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.payments (id, subscription_id, user_id, extra_order_id, amount, currency, method, status, gateway, gateway_order_id, gateway_txn_id, gateway_response, paid_at, refunded_at, refund_amount, failure_reason, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: subscription_packages; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.subscription_packages (id, subscription_id, package_id, quantity, unit_price, created_at) FROM stdin;
\.


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.subscriptions (id, user_id, vendor_id, plan_id, user_address_id, status, meal_slot, subscription_type, start_date, end_date, free_skips_total, free_skips_used, total_amount, discount_amount, final_amount, notes, cancelled_at, cancel_reason, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: wallet_transactions; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.wallet_transactions (id, wallet_id, user_id, type, reason, amount, balance_before, balance_after, reference_id, reference_type, description, created_by, created_at) FROM stdin;
\.


--
-- Data for Name: wallets; Type: TABLE DATA; Schema: subscription; Owner: postgres
--

COPY subscription.wallets (id, user_id, balance, created_at, updated_at) FROM stdin;
\.


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: auth; Owner: postgres
--

SELECT pg_catalog.setval('auth.users_id_seq', 1, true);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.audit_logs_id_seq', 1, false);


--
-- Name: menu_categories_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.menu_categories_id_seq', 7, true);


--
-- Name: menu_package_images_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.menu_package_images_id_seq', 2, true);


--
-- Name: menu_package_items_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.menu_package_items_id_seq', 12, true);


--
-- Name: menu_packages_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.menu_packages_id_seq', 4, true);


--
-- Name: service_unavailable_logs_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.service_unavailable_logs_id_seq', 1, true);


--
-- Name: serviceable_pincodes_pincode_id_seq; Type: SEQUENCE SET; Schema: master; Owner: postgres
--

SELECT pg_catalog.setval('master.serviceable_pincodes_pincode_id_seq', 3, true);


--
-- Name: provider_selected_packages_id_seq; Type: SEQUENCE SET; Schema: provider; Owner: postgres
--

SELECT pg_catalog.setval('provider.provider_selected_packages_id_seq', 2, true);


--
-- Name: providers_id_seq; Type: SEQUENCE SET; Schema: provider; Owner: postgres
--

SELECT pg_catalog.setval('provider.providers_id_seq', 3, true);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: otp_logs otp_logs_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.otp_logs
    ADD CONSTRAINT otp_logs_pkey PRIMARY KEY (id);


--
-- Name: user_addresses user_addresses_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_addresses
    ADD CONSTRAINT user_addresses_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_refresh_token_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_sessions
    ADD CONSTRAINT user_sessions_refresh_token_key UNIQUE (refresh_token);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_phone_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_phone_key UNIQUE (phone);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_referral_code_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_referral_code_key UNIQUE (referral_code);


--
-- Name: users users_user_id_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_user_id_key UNIQUE (user_id);


--
-- Name: admin_users admin_users_email_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.admin_users
    ADD CONSTRAINT admin_users_email_key UNIQUE (email);


--
-- Name: admin_users admin_users_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.admin_users
    ADD CONSTRAINT admin_users_pkey PRIMARY KEY (id);


--
-- Name: menu_categories menu_categories_category_id_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_categories
    ADD CONSTRAINT menu_categories_category_id_key UNIQUE (category_id);


--
-- Name: menu_categories menu_categories_category_slug_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_categories
    ADD CONSTRAINT menu_categories_category_slug_key UNIQUE (category_slug);


--
-- Name: menu_categories menu_categories_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_categories
    ADD CONSTRAINT menu_categories_pkey PRIMARY KEY (id);


--
-- Name: menu_package_images menu_package_images_image_id_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_images
    ADD CONSTRAINT menu_package_images_image_id_key UNIQUE (image_id);


--
-- Name: menu_package_images menu_package_images_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_images
    ADD CONSTRAINT menu_package_images_pkey PRIMARY KEY (id);


--
-- Name: menu_package_items menu_package_items_item_id_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_items
    ADD CONSTRAINT menu_package_items_item_id_key UNIQUE (item_id);


--
-- Name: menu_package_items menu_package_items_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_items
    ADD CONSTRAINT menu_package_items_pkey PRIMARY KEY (id);


--
-- Name: menu_packages menu_packages_package_id_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_packages
    ADD CONSTRAINT menu_packages_package_id_key UNIQUE (package_id);


--
-- Name: menu_packages menu_packages_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_packages
    ADD CONSTRAINT menu_packages_pkey PRIMARY KEY (id);


--
-- Name: service_unavailable_logs service_unavailable_logs_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.service_unavailable_logs
    ADD CONSTRAINT service_unavailable_logs_pkey PRIMARY KEY (id);


--
-- Name: serviceable_pincodes serviceable_pincodes_pincode_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.serviceable_pincodes
    ADD CONSTRAINT serviceable_pincodes_pincode_key UNIQUE (pincode);


--
-- Name: serviceable_pincodes serviceable_pincodes_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.serviceable_pincodes
    ADD CONSTRAINT serviceable_pincodes_pkey PRIMARY KEY (pincode_id);


--
-- Name: subscription_plans subscription_plans_pkey; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.subscription_plans
    ADD CONSTRAINT subscription_plans_pkey PRIMARY KEY (id);


--
-- Name: subscription_plans subscription_plans_subscription_type_meal_slot_key; Type: CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.subscription_plans
    ADD CONSTRAINT subscription_plans_subscription_type_meal_slot_key UNIQUE (subscription_type, meal_slot);


--
-- Name: complaints complaints_pkey; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.complaints
    ADD CONSTRAINT complaints_pkey PRIMARY KEY (id);


--
-- Name: otp_logs otp_logs_pkey; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.otp_logs
    ADD CONSTRAINT otp_logs_pkey PRIMARY KEY (otp_log_id);


--
-- Name: provider_selected_packages provider_selected_packages_pkey; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.provider_selected_packages
    ADD CONSTRAINT provider_selected_packages_pkey PRIMARY KEY (id);


--
-- Name: provider_selected_packages provider_selected_packages_selection_id_key; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.provider_selected_packages
    ADD CONSTRAINT provider_selected_packages_selection_id_key UNIQUE (selection_id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);


--
-- Name: providers uq_provider_provider_id; Type: CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.providers
    ADD CONSTRAINT uq_provider_provider_id UNIQUE (provider_id);


--
-- Name: extra_orders extra_orders_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.extra_orders
    ADD CONSTRAINT extra_orders_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: orders orders_subscription_id_order_date_meal_slot_key; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_subscription_id_order_date_meal_slot_key UNIQUE (subscription_id, order_date, meal_slot);


--
-- Name: payments payments_gateway_txn_id_key; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.payments
    ADD CONSTRAINT payments_gateway_txn_id_key UNIQUE (gateway_txn_id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: subscription_packages subscription_packages_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscription_packages
    ADD CONSTRAINT subscription_packages_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: wallet_transactions wallet_transactions_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallet_transactions
    ADD CONSTRAINT wallet_transactions_pkey PRIMARY KEY (id);


--
-- Name: wallets wallets_pkey; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallets
    ADD CONSTRAINT wallets_pkey PRIMARY KEY (id);


--
-- Name: wallets wallets_user_id_key; Type: CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallets
    ADD CONSTRAINT wallets_user_id_key UNIQUE (user_id);


--
-- Name: idx_notifications_unread; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_notifications_unread ON auth.notifications USING btree (user_id) WHERE (is_read = false);


--
-- Name: idx_notifications_user; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_notifications_user ON auth.notifications USING btree (user_id, is_read, created_at DESC);


--
-- Name: idx_otp_contact_purpose; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_otp_contact_purpose ON auth.otp_logs USING btree (contact, purpose, is_used);


--
-- Name: idx_user_addresses_pincode; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_user_addresses_pincode ON auth.user_addresses USING btree (pin_code) WHERE (is_active = true);


--
-- Name: idx_user_addresses_user; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_user_addresses_user ON auth.user_addresses USING btree (user_id) WHERE (is_active = true);


--
-- Name: idx_users_email; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_users_email ON auth.users USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: idx_users_phone; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_users_phone ON auth.users USING btree (phone) WHERE (deleted_at IS NULL);


--
-- Name: idx_users_status; Type: INDEX; Schema: auth; Owner: postgres
--

CREATE INDEX idx_users_status ON auth.users USING btree (status) WHERE (deleted_at IS NULL);


--
-- Name: idx_audit_changed_by; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_audit_changed_by ON ONLY master.audit_logs USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_01_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_01_changed_by_idx ON master.audit_logs_2025_01 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: idx_audit_table_record; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_audit_table_record ON ONLY master.audit_logs USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_01_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_01_table_name_record_id_idx ON master.audit_logs_2025_01 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_02_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_02_changed_by_idx ON master.audit_logs_2025_02 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_02_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_02_table_name_record_id_idx ON master.audit_logs_2025_02 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_03_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_03_changed_by_idx ON master.audit_logs_2025_03 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_03_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_03_table_name_record_id_idx ON master.audit_logs_2025_03 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_04_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_04_changed_by_idx ON master.audit_logs_2025_04 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_04_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_04_table_name_record_id_idx ON master.audit_logs_2025_04 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_05_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_05_changed_by_idx ON master.audit_logs_2025_05 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_05_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_05_table_name_record_id_idx ON master.audit_logs_2025_05 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_06_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_06_changed_by_idx ON master.audit_logs_2025_06 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_06_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_06_table_name_record_id_idx ON master.audit_logs_2025_06 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_07_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_07_changed_by_idx ON master.audit_logs_2025_07 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_07_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_07_table_name_record_id_idx ON master.audit_logs_2025_07 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_08_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_08_changed_by_idx ON master.audit_logs_2025_08 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_08_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_08_table_name_record_id_idx ON master.audit_logs_2025_08 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_09_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_09_changed_by_idx ON master.audit_logs_2025_09 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_09_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_09_table_name_record_id_idx ON master.audit_logs_2025_09 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_10_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_10_changed_by_idx ON master.audit_logs_2025_10 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_10_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_10_table_name_record_id_idx ON master.audit_logs_2025_10 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_11_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_11_changed_by_idx ON master.audit_logs_2025_11 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_11_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_11_table_name_record_id_idx ON master.audit_logs_2025_11 USING btree (table_name, record_id);


--
-- Name: audit_logs_2025_12_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_12_changed_by_idx ON master.audit_logs_2025_12 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2025_12_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2025_12_table_name_record_id_idx ON master.audit_logs_2025_12 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_01_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_01_changed_by_idx ON master.audit_logs_2026_01 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_01_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_01_table_name_record_id_idx ON master.audit_logs_2026_01 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_02_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_02_changed_by_idx ON master.audit_logs_2026_02 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_02_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_02_table_name_record_id_idx ON master.audit_logs_2026_02 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_03_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_03_changed_by_idx ON master.audit_logs_2026_03 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_03_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_03_table_name_record_id_idx ON master.audit_logs_2026_03 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_04_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_04_changed_by_idx ON master.audit_logs_2026_04 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_04_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_04_table_name_record_id_idx ON master.audit_logs_2026_04 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_05_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_05_changed_by_idx ON master.audit_logs_2026_05 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_05_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_05_table_name_record_id_idx ON master.audit_logs_2026_05 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_06_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_06_changed_by_idx ON master.audit_logs_2026_06 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_06_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_06_table_name_record_id_idx ON master.audit_logs_2026_06 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_07_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_07_changed_by_idx ON master.audit_logs_2026_07 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_07_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_07_table_name_record_id_idx ON master.audit_logs_2026_07 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_08_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_08_changed_by_idx ON master.audit_logs_2026_08 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_08_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_08_table_name_record_id_idx ON master.audit_logs_2026_08 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_09_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_09_changed_by_idx ON master.audit_logs_2026_09 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_09_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_09_table_name_record_id_idx ON master.audit_logs_2026_09 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_10_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_10_changed_by_idx ON master.audit_logs_2026_10 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_10_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_10_table_name_record_id_idx ON master.audit_logs_2026_10 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_11_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_11_changed_by_idx ON master.audit_logs_2026_11 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_11_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_11_table_name_record_id_idx ON master.audit_logs_2026_11 USING btree (table_name, record_id);


--
-- Name: audit_logs_2026_12_changed_by_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_12_changed_by_idx ON master.audit_logs_2026_12 USING btree (changed_by) WHERE (changed_by IS NOT NULL);


--
-- Name: audit_logs_2026_12_table_name_record_id_idx; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX audit_logs_2026_12_table_name_record_id_idx ON master.audit_logs_2026_12 USING btree (table_name, record_id);


--
-- Name: idx_menu_packages_active; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_menu_packages_active ON master.menu_packages USING btree (is_active);


--
-- Name: idx_menu_packages_available; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_menu_packages_available ON master.menu_packages USING btree (is_available);


--
-- Name: idx_menu_packages_category; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_menu_packages_category ON master.menu_packages USING btree (category_id);


--
-- Name: idx_menu_packages_provider; Type: INDEX; Schema: master; Owner: postgres
--

CREATE INDEX idx_menu_packages_provider ON master.menu_packages USING btree (provider_id);


--
-- Name: idx_complaints_status; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE INDEX idx_complaints_status ON provider.complaints USING btree (status) WHERE (status = ANY (ARRAY['open'::public.complaint_status, 'investigating'::public.complaint_status]));


--
-- Name: idx_complaints_user; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE INDEX idx_complaints_user ON provider.complaints USING btree (user_id, created_at DESC);


--
-- Name: idx_complaints_vendor; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE INDEX idx_complaints_vendor ON provider.complaints USING btree (vendor_id, status);


--
-- Name: idx_reviews_pkg; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE INDEX idx_reviews_pkg ON provider.reviews USING btree (package_id) WHERE (package_id IS NOT NULL);


--
-- Name: idx_reviews_unique_daily; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE UNIQUE INDEX idx_reviews_unique_daily ON provider.reviews USING btree (user_id, vendor_id, review_date);


--
-- Name: idx_reviews_vendor; Type: INDEX; Schema: provider; Owner: postgres
--

CREATE INDEX idx_reviews_vendor ON provider.reviews USING btree (vendor_id, created_at DESC) WHERE (is_visible = true);


--
-- Name: idx_extra_orders_user; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_extra_orders_user ON subscription.extra_orders USING btree (user_id, delivery_date DESC);


--
-- Name: idx_extra_orders_vendor; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_extra_orders_vendor ON subscription.extra_orders USING btree (vendor_id, delivery_date);


--
-- Name: idx_orders_date_status; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_orders_date_status ON subscription.orders USING btree (order_date, status);


--
-- Name: idx_orders_sub; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_orders_sub ON subscription.orders USING btree (subscription_id);


--
-- Name: idx_orders_user; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_orders_user ON subscription.orders USING btree (user_id, order_date DESC);


--
-- Name: idx_orders_vendor; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_orders_vendor ON subscription.orders USING btree (vendor_id, order_date);


--
-- Name: idx_sub_packages_subscription; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_sub_packages_subscription ON subscription.subscription_packages USING btree (subscription_id);


--
-- Name: idx_subscriptions_dates; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_subscriptions_dates ON subscription.subscriptions USING btree (start_date, end_date);


--
-- Name: idx_subscriptions_status; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_subscriptions_status ON subscription.subscriptions USING btree (status);


--
-- Name: idx_subscriptions_user; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_subscriptions_user ON subscription.subscriptions USING btree (user_id);


--
-- Name: idx_subscriptions_vendor; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_subscriptions_vendor ON subscription.subscriptions USING btree (vendor_id);


--
-- Name: idx_wallet_txn_user; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_wallet_txn_user ON subscription.wallet_transactions USING btree (user_id, created_at DESC);


--
-- Name: idx_wallet_txn_wallet; Type: INDEX; Schema: subscription; Owner: postgres
--

CREATE INDEX idx_wallet_txn_wallet ON subscription.wallet_transactions USING btree (wallet_id, created_at DESC);


--
-- Name: audit_logs_2025_01_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_01_changed_by_idx;


--
-- Name: audit_logs_2025_01_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_01_table_name_record_id_idx;


--
-- Name: audit_logs_2025_02_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_02_changed_by_idx;


--
-- Name: audit_logs_2025_02_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_02_table_name_record_id_idx;


--
-- Name: audit_logs_2025_03_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_03_changed_by_idx;


--
-- Name: audit_logs_2025_03_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_03_table_name_record_id_idx;


--
-- Name: audit_logs_2025_04_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_04_changed_by_idx;


--
-- Name: audit_logs_2025_04_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_04_table_name_record_id_idx;


--
-- Name: audit_logs_2025_05_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_05_changed_by_idx;


--
-- Name: audit_logs_2025_05_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_05_table_name_record_id_idx;


--
-- Name: audit_logs_2025_06_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_06_changed_by_idx;


--
-- Name: audit_logs_2025_06_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_06_table_name_record_id_idx;


--
-- Name: audit_logs_2025_07_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_07_changed_by_idx;


--
-- Name: audit_logs_2025_07_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_07_table_name_record_id_idx;


--
-- Name: audit_logs_2025_08_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_08_changed_by_idx;


--
-- Name: audit_logs_2025_08_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_08_table_name_record_id_idx;


--
-- Name: audit_logs_2025_09_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_09_changed_by_idx;


--
-- Name: audit_logs_2025_09_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_09_table_name_record_id_idx;


--
-- Name: audit_logs_2025_10_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_10_changed_by_idx;


--
-- Name: audit_logs_2025_10_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_10_table_name_record_id_idx;


--
-- Name: audit_logs_2025_11_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_11_changed_by_idx;


--
-- Name: audit_logs_2025_11_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_11_table_name_record_id_idx;


--
-- Name: audit_logs_2025_12_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2025_12_changed_by_idx;


--
-- Name: audit_logs_2025_12_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2025_12_table_name_record_id_idx;


--
-- Name: audit_logs_2026_01_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_01_changed_by_idx;


--
-- Name: audit_logs_2026_01_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_01_table_name_record_id_idx;


--
-- Name: audit_logs_2026_02_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_02_changed_by_idx;


--
-- Name: audit_logs_2026_02_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_02_table_name_record_id_idx;


--
-- Name: audit_logs_2026_03_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_03_changed_by_idx;


--
-- Name: audit_logs_2026_03_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_03_table_name_record_id_idx;


--
-- Name: audit_logs_2026_04_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_04_changed_by_idx;


--
-- Name: audit_logs_2026_04_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_04_table_name_record_id_idx;


--
-- Name: audit_logs_2026_05_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_05_changed_by_idx;


--
-- Name: audit_logs_2026_05_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_05_table_name_record_id_idx;


--
-- Name: audit_logs_2026_06_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_06_changed_by_idx;


--
-- Name: audit_logs_2026_06_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_06_table_name_record_id_idx;


--
-- Name: audit_logs_2026_07_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_07_changed_by_idx;


--
-- Name: audit_logs_2026_07_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_07_table_name_record_id_idx;


--
-- Name: audit_logs_2026_08_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_08_changed_by_idx;


--
-- Name: audit_logs_2026_08_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_08_table_name_record_id_idx;


--
-- Name: audit_logs_2026_09_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_09_changed_by_idx;


--
-- Name: audit_logs_2026_09_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_09_table_name_record_id_idx;


--
-- Name: audit_logs_2026_10_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_10_changed_by_idx;


--
-- Name: audit_logs_2026_10_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_10_table_name_record_id_idx;


--
-- Name: audit_logs_2026_11_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_11_changed_by_idx;


--
-- Name: audit_logs_2026_11_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_11_table_name_record_id_idx;


--
-- Name: audit_logs_2026_12_changed_by_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_changed_by ATTACH PARTITION master.audit_logs_2026_12_changed_by_idx;


--
-- Name: audit_logs_2026_12_table_name_record_id_idx; Type: INDEX ATTACH; Schema: master; Owner: postgres
--

ALTER INDEX master.idx_audit_table_record ATTACH PARTITION master.audit_logs_2026_12_table_name_record_id_idx;


--
-- Name: users fk_referred_by; Type: FK CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT fk_referred_by FOREIGN KEY (referred_by) REFERENCES auth.users(user_id) ON DELETE SET NULL;


--
-- Name: user_sessions fk_sessions_user; Type: FK CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_sessions
    ADD CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES auth.users(user_id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: user_addresses user_addresses_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_addresses
    ADD CONSTRAINT user_addresses_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id) ON DELETE CASCADE;


--
-- Name: menu_packages fk_category; Type: FK CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_packages
    ADD CONSTRAINT fk_category FOREIGN KEY (category_id) REFERENCES master.menu_categories(category_id);


--
-- Name: menu_package_items fk_package; Type: FK CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_items
    ADD CONSTRAINT fk_package FOREIGN KEY (package_id) REFERENCES master.menu_packages(package_id) ON DELETE CASCADE;


--
-- Name: menu_package_images fk_package_image; Type: FK CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_package_images
    ADD CONSTRAINT fk_package_image FOREIGN KEY (package_id) REFERENCES master.menu_packages(package_id) ON DELETE CASCADE;


--
-- Name: menu_packages fk_provider; Type: FK CONSTRAINT; Schema: master; Owner: postgres
--

ALTER TABLE ONLY master.menu_packages
    ADD CONSTRAINT fk_provider FOREIGN KEY (provider_id) REFERENCES provider.providers(provider_id);


--
-- Name: complaints complaints_order_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.complaints
    ADD CONSTRAINT complaints_order_id_fkey FOREIGN KEY (order_id) REFERENCES subscription.orders(id);


--
-- Name: complaints complaints_subscription_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.complaints
    ADD CONSTRAINT complaints_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES subscription.subscriptions(id);


--
-- Name: complaints complaints_user_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.complaints
    ADD CONSTRAINT complaints_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: complaints complaints_vendor_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.complaints
    ADD CONSTRAINT complaints_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES provider.providers(provider_id);


--
-- Name: reviews reviews_order_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_order_id_fkey FOREIGN KEY (order_id) REFERENCES subscription.orders(id);


--
-- Name: reviews reviews_package_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_package_id_fkey FOREIGN KEY (package_id) REFERENCES master.menu_packages(package_id);


--
-- Name: reviews reviews_subscription_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES subscription.subscriptions(id);


--
-- Name: reviews reviews_user_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: reviews reviews_vendor_id_fkey; Type: FK CONSTRAINT; Schema: provider; Owner: postgres
--

ALTER TABLE ONLY provider.reviews
    ADD CONSTRAINT reviews_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES provider.providers(provider_id);


--
-- Name: extra_orders extra_orders_address_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.extra_orders
    ADD CONSTRAINT extra_orders_address_id_fkey FOREIGN KEY (address_id) REFERENCES auth.user_addresses(id);


--
-- Name: extra_orders extra_orders_package_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.extra_orders
    ADD CONSTRAINT extra_orders_package_id_fkey FOREIGN KEY (package_id) REFERENCES master.menu_packages(package_id);


--
-- Name: extra_orders extra_orders_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.extra_orders
    ADD CONSTRAINT extra_orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: extra_orders extra_orders_vendor_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.extra_orders
    ADD CONSTRAINT extra_orders_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES provider.providers(provider_id);


--
-- Name: orders orders_delivery_address_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_delivery_address_id_fkey FOREIGN KEY (delivery_address_id) REFERENCES auth.user_addresses(id);


--
-- Name: orders orders_subscription_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES subscription.subscriptions(id);


--
-- Name: orders orders_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: orders orders_vendor_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.orders
    ADD CONSTRAINT orders_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES provider.providers(provider_id);


--
-- Name: payments payments_extra_order_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.payments
    ADD CONSTRAINT payments_extra_order_id_fkey FOREIGN KEY (extra_order_id) REFERENCES subscription.extra_orders(id);


--
-- Name: payments payments_subscription_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.payments
    ADD CONSTRAINT payments_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES subscription.subscriptions(id);


--
-- Name: payments payments_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.payments
    ADD CONSTRAINT payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: subscription_packages subscription_packages_package_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscription_packages
    ADD CONSTRAINT subscription_packages_package_id_fkey FOREIGN KEY (package_id) REFERENCES master.menu_packages(package_id);


--
-- Name: subscription_packages subscription_packages_subscription_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscription_packages
    ADD CONSTRAINT subscription_packages_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES subscription.subscriptions(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_plan_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES master.subscription_plans(id);


--
-- Name: subscriptions subscriptions_user_address_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscriptions
    ADD CONSTRAINT subscriptions_user_address_id_fkey FOREIGN KEY (user_address_id) REFERENCES auth.user_addresses(id);


--
-- Name: subscriptions subscriptions_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: subscriptions subscriptions_vendor_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.subscriptions
    ADD CONSTRAINT subscriptions_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES provider.providers(provider_id);


--
-- Name: wallet_transactions wallet_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallet_transactions
    ADD CONSTRAINT wallet_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id);


--
-- Name: wallet_transactions wallet_transactions_wallet_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallet_transactions
    ADD CONSTRAINT wallet_transactions_wallet_id_fkey FOREIGN KEY (wallet_id) REFERENCES subscription.wallets(id);


--
-- Name: wallets wallets_user_id_fkey; Type: FK CONSTRAINT; Schema: subscription; Owner: postgres
--

ALTER TABLE ONLY subscription.wallets
    ADD CONSTRAINT wallets_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(user_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict eImhxaDTq4BHGS04UpupIhxfhkeAEM8z1PCRi0VAS5ZcipkdJS9QhfxP9MD5WuX

