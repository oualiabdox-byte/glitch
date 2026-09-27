from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAExecutionEvent
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOADealStatus,
    ProtoOAExecutionType,
    ProtoOAOrderStatus,
    ProtoOAOrderType,
    ProtoOATradeSide,
)

from execution.ctrader_adapter import CTraderAdapter


def test_execution_event_normalization_preserves_raw_event_and_ids():
    event = ProtoOAExecutionEvent(
        ctidTraderAccountId=7,
        executionType=ProtoOAExecutionType.Value("ORDER_PARTIAL_FILL"),
    )
    event.order.orderId = 91
    event.order.clientOrderId = "client-1"
    event.order.orderType = ProtoOAOrderType.Value("MARKET")
    event.order.orderStatus = ProtoOAOrderStatus.Value("ORDER_STATUS_ACCEPTED")
    event.order.tradeData.symbolId = 42
    event.order.tradeData.tradeSide = ProtoOATradeSide.Value("BUY")
    event.order.tradeData.volume = 40000
    event.order.executedVolume = 40000
    event.order.executionPrice = 1.101
    event.deal.dealId = 501
    event.deal.orderId = 91
    event.deal.positionId = 601
    event.deal.volume = 40000
    event.deal.filledVolume = 40000
    event.deal.symbolId = 42
    event.deal.createTimestamp = 1
    event.deal.executionTimestamp = 1
    event.deal.tradeSide = ProtoOATradeSide.Value("BUY")
    event.deal.dealStatus = ProtoOADealStatus.Value("FILLED")
    event.deal.executionPrice = 1.101
    envelope = ProtoMessage(
        payloadType=event.payloadType,
        payload=event.SerializeToString(),
        clientMsgId="int-1",
    )
    adapter = CTraderAdapter.__new__(CTraderAdapter)
    adapter.account_id = 7
    normalized = adapter._normalize_broker_event(envelope, event, "execution")
    assert normalized["execution_type"] == "ORDER_PARTIAL_FILL"
    assert normalized["client_msg_id"] == "int-1"
    assert normalized["broker_order_id"] == 91
    assert normalized["deal_id"] == 501
    assert normalized["position_id"] == 601
    assert normalized["executed_volume"] == 400.0
    assert normalized["last_volume"] == 400.0
    assert normalized["raw_payload_hex"] == envelope.SerializeToString().hex()
    assert normalized["raw_event"]["executionType"] == "ORDER_PARTIAL_FILL"
