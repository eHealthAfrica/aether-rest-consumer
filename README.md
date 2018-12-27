# aether-rest-consumer
An Aether consumer that publishes to REST endpoints

## Specification

## Data Definitions

### Jobs:
 _list_jobs_
 - [_job1_, _job2_, _job3_, _..._]

### Job: 
 _job:{id}_
 - ID : str
 - Owner : str
 - Modified : str (generated)
 - Hash : str (generated)
 - Type : str (REST type)
 - Topic : [topic1, topic2, ...]
 - DataMap: { key : jsonpath_expr, ... } 
     - like "schema_name" : "$.schema.name" or "id" : "$.msg.id"
 - URL : str (template) 
     - w/ key replacement from datamap like 'http://example.com/{id}'
 
#### Optional:
 - basic_auth: {user: user, pw: pw}
 - token: token for auth
 - query_params : [ keys from datamap ] 
     - becomes ?key1=value1&key2=value2...
 - json_body (post only) : [ keys from datamap ]
     - becomes { key1 : val1, key2: val2 }


## API

 - /jobs/{owner}
    - GET -- list all jobs for owner
 - /job/{id}
    - GET -- get job details
    - POST -- submit JSON to upsert a job

## Consumer Behavior

The consumer will look for fully formed job declarations in a config folder in case we need to have declarative definitions for a particular solution. If a job exists with the same ID, the existing job takes precidence so file config is only useful for creating jobs once. After launch, jobs can be added and controlled via the API. We'll run each job in its own thread. Commands from API -> job handlers will happen via pub/sub on 'msg/job:{id}' since we're using Redis already. Jobs will process each message on the subscibed topics, perform the limited extraction described in the job to create a REST request, and send the data to the prescribed endpoint. Failures and exceptions will be logged with the offending entity and job id.

## Planned Improvements ( currently out of scope )

### Data Structures
 - job/Ratelimit : float ( slow down requests from this channel by sleeping {n} fractional seconds between sending messages )

### API

 - /job/{id}/{ start | stop }
 - /job/{id}/set_offset/{offset}  

### Behavior

 - Failures should be retried on 500x response 
