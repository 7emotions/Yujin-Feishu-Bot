from plugins.chat.plugin import ChatPlugin
from plugins.reimbursement.plugin import ReimbursementPlugin
from runtime.router import FeishuBot


bot = FeishuBot()
reimbursement_plugin = ReimbursementPlugin()
chat_plugin = ChatPlugin(lambda: bot._plugins)
bot.register_plugin(reimbursement_plugin)
bot.register_plugin(chat_plugin)
