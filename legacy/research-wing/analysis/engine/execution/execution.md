# Execution Architecture (Detailed)

The execution subsystem separates strategy intent from simulated market execution.

Execution flow:

Signal
↓
Broker
↓
Order
↓
Matcher
↓
Trade
↓
Portfolio



---

## Broker

The Broker converts strategy Signals into executable Orders.

The Broker represents the boundary between:

**Strategy intent**

and

**Execution instructions**

Responsibilities:

- translate `SignalAction` into `OrderSide`
- resolve position sizing
- create executable Orders
- attach execution metadata

The Broker does not:

- execute orders
- determine fills
- calculate commissions
- apply slippage
- update portfolio state

The Broker receives a restricted execution context rather than direct engine access.

This prevents execution logic from becoming coupled to portfolio internals.

---

## Execution Context

Execution components receive read-only adapters containing only required information.

`PortfolioBrokerContext` provides the Broker with:

- current portfolio equity
- current positions
- available prices

The context does not allow:

- portfolio mutation
- trade creation
- position updates

This maintains the execution boundary:

Portfolio
↓
Execution Context
↓
Broker

rather than:

Broker
↓
Portfolio mutation


---

## Matcher

The Matcher simulates exchange execution.

Responsibilities:

- validate Orders
- determine execution timestamp
- apply latency
- calculate execution price
- apply slippage
- calculate fees
- convert filled Orders into immutable Trades

The Matcher does not:

- create Orders
- generate Signals
- manage Positions
- update Portfolios

Execution flow:
Order
|
+--> Latency Model
|
+--> Slippage Model
|
+--> Fee Model
|
v
Trade


---

## Fee Models

Fees are isolated behind the `FeeModel` interface.

A fee model answers:

> Given this execution, what cost applies?

Supported models:

- zero-fee execution
- percentage maker/taker fees

Fee models:

- do not create trades
- do not modify orders
- do not update accounts

They only calculate execution costs.

---

## Slippage Models

Slippage models represent the difference between expected market price and actual execution price.

Supported models:

- no slippage
- percentage slippage
- fixed basis-point slippage
- linear impact slippage

The slippage layer allows execution realism to evolve independently from:

- strategies
- portfolio accounting
- market data

Future implementations may include:

- order book depth
- volume participation
- market impact models

---

## Latency Models

Latency models represent the delay between:

strategy decision time

and

actual execution time.

Latency models are deterministic transformations.

They do not:

- wait in real time
- control simulation progression
- modify orders

Current implementations:

- zero latency
- fixed delay
- millisecond delay

Future implementations may model:

- network latency
- exchange queue delay
- infrastructure differences

---

## Execution Isolation Principle

The execution engine follows:
Strategy
|
| Signal
↓
Broker
|
| Order
↓
Matcher
|
| Trade
↓
Portfolio


No component skips layers.

This prevents:

- strategies bypassing execution costs
- brokers modifying portfolio state
- portfolios depending on execution implementation

