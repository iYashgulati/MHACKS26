from integrations.photon import recieve_message
from agent.claude_runner import run_agent 


def main():
    user_message = ( "What do you want the AI agent to do?" )

    run_agent(
        prompt=user_message, 
        repo="./repo/demo_repo"
    )

