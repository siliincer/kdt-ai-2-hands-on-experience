# sqlalchemy의 세션(Session)과 트랜잭션(Transaction) 동작에 대한 이해

1. add: 임시 저장동작: 객체를 세션(Session)의 관리 대상(Pending 상태)으로
   등록합니다.트랜잭션 관점: 아직 데이터베이스에 쿼리를 보내지 않습니다.
   트랜잭션 시작 전이나 진행 중에 메모리에 데이터를 올려두는 단계입니다.

2. flush: DB 동기화 (트랜잭션 내부)동작: 세션에 쌓인 변경 사항
   (INSERT, UPDATE, DELETE)을 실제 데이터베이스로 보냅니다.

트랜잭션 관점: 데이터베이스 작업이 수행됩니다. 하지만 아직 트랜잭션이 종료된 것은
아닙니다. 따라서 다른 세션에서는 이 변경 사항을 볼 수 없습니다.
에러 발생 시 롤백(Rollback)이 가능합니다.

3. commit: 트랜잭션 종료 및 영구 반영동작: 내부적으로 flush를 실행한 후,

변경 사항을 데이터베이스에 완전히 영구 반영합니다.
트랜잭션 관점: 트랜잭션을 닫고(close) 결과를 확정 짓습니다.
이 작업이 끝나면 다른 세션에서도 변경된 데이터를 조회할 수 있습니다.

4. refresh: DB 데이터로 객체 새로고침동작: 데이터베이스에 있는 최신 데이터로
   객체의 속성을 다시 덮어씁니다.

트랜잭션 관점: 데이터베이스에서 데이터를 읽어와야 하므로,
내부적으로 flush가 먼저 실행되어 메모리의 변경 사항을 DB에 반영한 후
최신 상태를 가져옵니다. 주로 DB에서 자동 생성된 id나 created_at 등을
가져올 때 사용합니다.

# autobegin의 정확한 위치 — ORM 계층의 편의 기능

먼저 개념을 명확히 구분할 필요가 있습니다. "autobegin"은 SQLAlchemy Session 객체가 제공하는 편의 기능이며, PostgreSQL이나 DBAPI(asyncpg) 자체의 성능 특성과는 별개의 계층입니다.

Session.autobegin(SQLAlchemy 1.4 이상 기본값 True)이 하는 일은, 개발자가 매번 session.begin()을 명시적으로 호출하지 않아도 session.execute() 등이 실행되는 시점에 SQLAlchemy가 대신 트랜잭션 블록을 논리적으로 "열어주는" 것뿐입니다.

즉, autobegin을 끄더라도(autobegin=False) 개발자가 매 요청마다 async with session.begin(): 혹은 await session.begin()을 직접 호출해야 하며, 이 경우 실제로 PostgreSQL 서버에 전송되는 BEGIN 명령 자체는 동일하게 발생합니다.

# 진짜 트레이드오프는 다른 축에 있음 — Isolation Level

성능과 편의성 사이의 실질적인 트레이드오프는 autobegin의 on/off가 아니라, 트랜잭션을 감싸는 방식 자체(non-autocommit) vs 진정한 autocommit isolation level 사이에 존재합니다.

SQLAlchemy는 isolation_level="AUTOCOMMIT"을 엔진 또는 커넥션 단위로 지정할 수 있는 옵션을 제공합니다. 이 모드에서는 각 SQL 문이 독립적으로 즉시 커밋되어 BEGIN/COMMIT(또는 ROLLBACK)으로 감싸는 왕복 자체가 발생하지 않습니다. 다만 이는 다음과 같은 명확한 대가를 수반합니다.
