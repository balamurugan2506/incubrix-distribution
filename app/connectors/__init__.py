"""Connectors module initialization and automatic registration."""

from app.connectors.registry import registry
from app.connectors.discourse import DiscourseConnector
from app.connectors.lemmy import LemmyConnector
from app.connectors.devto import DevtoConnector
from app.connectors.ghost import GhostConnector
from app.connectors.signed_webhook import SignedWebhookConnector
from app.connectors.assisted import AssistedConnector
from app.connectors.hashnode import HashnodeConnector
from app.connectors.slack import SlackConnector
from app.connectors.mailchimp import MailchimpConnector

# Register all 6 Core connector classes
registry.register_connector(DiscourseConnector)
registry.register_connector(LemmyConnector)
registry.register_connector(DevtoConnector)
registry.register_connector(GhostConnector)
registry.register_connector(SignedWebhookConnector)
registry.register_connector(AssistedConnector)

# Register 3 Advanced connector classes (Advanced Level 5)
registry.register_connector(HashnodeConnector)
registry.register_connector(SlackConnector)
registry.register_connector(MailchimpConnector)

registry.load_manifests()
