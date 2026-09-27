from twisted.internet.defer import Deferred

from ctrader_open_api import Client, Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAExecutionEvent
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAExecutionType


def test_sdk_delivers_execution_event_to_message_callback_and_deferred():
    """Pin the SDK 0.9.2 delivery contract without connecting to cTrader."""
    client = Client.__new__(Client)
    received = []
    callback_values = []
    client._messageReceivedCallback = lambda _client, message: received.append(
        Protobuf.extract(message)
    )
    client._responseDeferreds = {}

    deferred = Deferred()
    deferred.addCallback(callback_values.append)
    client._responseDeferreds["order-1"] = deferred

    event = ProtoOAExecutionEvent(
        ctidTraderAccountId=42,
        executionType=ProtoOAExecutionType.Value("ORDER_ACCEPTED"),
    )
    envelope = ProtoMessage(
        payloadType=event.payloadType,
        payload=event.SerializeToString(),
        clientMsgId="order-1",
    )

    client._received(envelope)

    assert received[0].executionType == ProtoOAExecutionType.Value("ORDER_ACCEPTED")
    assert callback_values[0] == envelope
    assert "order-1" not in client._responseDeferreds
