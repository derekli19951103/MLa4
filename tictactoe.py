from __future__ import print_function
from collections import defaultdict
from itertools import count
import numpy as np
import math
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.distributions
from torch.autograd import Variable


class Environment(object):
    """
    The Tic-Tac-Toe Environment
    """
    # possible ways to win
    win_set = frozenset([(0, 1, 2), (3, 4, 5), (6, 7, 8),  # horizontal
                         (0, 3, 6), (1, 4, 7), (2, 5, 8),  # vertical
                         (0, 4, 8), (2, 4, 6)])  # diagonal
    # statuses
    STATUS_VALID_MOVE = 'valid'
    STATUS_INVALID_MOVE = 'inv'
    STATUS_WIN = 'win'
    STATUS_TIE = 'tie'
    STATUS_LOSE = 'lose'
    STATUS_DONE = 'done'

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the game to an empty board."""
        self.grid = np.array([0] * 9)  # grid
        self.turn = 1  # whose turn it is
        self.done = False  # whether game is done
        return self.grid

    def render(self):
        """Print what is on the board."""
        map = {0: '.', 1: 'x', 2: 'o'}  # grid label vs how to plot
        print(''.join(map[i] for i in self.grid[0:3]))
        print(''.join(map[i] for i in self.grid[3:6]))
        print(''.join(map[i] for i in self.grid[6:9]))
        print('====')

    def check_win(self):
        """Check if someone has won the game."""
        for pos in self.win_set:
            s = set([self.grid[p] for p in pos])
            if len(s) == 1 and (0 not in s):
                return True
        return False

    def step(self, action):
        """Mark a point on position action."""
        assert type(action) == int and action >= 0 and action < 9
        # done = already finished the game
        if self.done:
            return self.grid, self.STATUS_DONE, self.done
        # action already have something on it
        if self.grid[action] != 0:
            return self.grid, self.STATUS_INVALID_MOVE, self.done
        # play move
        self.grid[action] = self.turn
        if self.turn == 1:
            self.turn = 2
        else:
            self.turn = 1
        # check win
        if self.check_win():
            self.done = True
            return self.grid, self.STATUS_WIN, self.done
        # check tie
        if all([p != 0 for p in self.grid]):
            self.done = True
            return self.grid, self.STATUS_TIE, self.done
        return self.grid, self.STATUS_VALID_MOVE, self.done

    def random_step(self):
        """Choose a random, unoccupied move on the board to play."""
        pos = [i for i in range(9) if self.grid[i] == 0]
        move = random.choice(pos)
        return self.step(move)

    def play_against_random(self, action):
        """Play a move, and then have a random agent play the next move."""
        state, status, done = self.step(action)
        if not done and self.turn == 2:
            state, s2, done = self.random_step()
            if done:
                if s2 == self.STATUS_WIN:
                    status = self.STATUS_LOSE
                elif s2 == self.STATUS_TIE:
                    status = self.STATUS_TIE
                else:
                    raise ValueError("???")
        return state, status, done


class Policy(nn.Module):
    """
    The Tic-Tac-Toe Policy
    """

    def __init__(self, input_size=27, hidden_size=128, output_size=9):
        super(Policy, self).__init__()
        self.affine1 = nn.Linear(input_size, hidden_size)
        self.affine2 = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        x = F.relu(self.affine1(x))
        action_scores = self.affine2(x)
        return F.softmax(action_scores, dim=1)


def select_action(policy, state):
    """Samples an action from the policy at the state."""
    state = torch.from_numpy(state).long().unsqueeze(0)
    state = torch.zeros(3, 9).scatter_(0, state, 1).view(1, 27)
    pr = policy(Variable(state))
    m = torch.distributions.Categorical(pr)
    action = m.sample()
    log_prob = torch.sum(m.log_prob(action))
    return action.data[0], log_prob


def compute_returns(rewards, gamma=1.0):
    """
    Compute returns for each time step, given the rewards
      @param rewards: list of floats, where rewards[t] is the reward
                      obtained at time step t
      @param gamma: the discount factor
      @returns list of floats representing the episode's returns
          G_t = r_t + \gamma r_{t+1} + \gamma^2 r_{t+2} + ...

    """
    R = np.array(rewards)
    steps = np.array(list(range(len(rewards))))
    gammas = np.array([gamma] * len(rewards))
    powers = np.power(gammas, steps)
    G_ts = []
    for i in range(len(rewards)):
        G_ts.append(np.dot(R[i:].T, powers[:len(rewards) - i]))
    return G_ts


def finish_episode(saved_rewards, saved_logprobs, gamma=1.0):
    """Samples an action from the policy at the state."""
    policy_loss = []
    returns = compute_returns(saved_rewards, gamma)
    returns = torch.Tensor(returns)
    # subtract mean and std for faster training
    returns = (returns - returns.mean()) / (returns.std() +
                                            np.finfo(np.float32).eps)
    for log_prob, reward in zip(saved_logprobs, returns):
        policy_loss.append(-log_prob * reward)
    policy_loss = torch.cat(policy_loss).sum()
    policy_loss.backward(retain_graph=True)
    # note: retain_graph=True allows for multiple calls to .backward()
    # in a single step


def get_reward(status):
    """Returns a numeric given an environment status."""
    return {
        Environment.STATUS_VALID_MOVE: 0,
        Environment.STATUS_INVALID_MOVE: -100,
        Environment.STATUS_WIN: 4,
        Environment.STATUS_TIE: 1,
        Environment.STATUS_LOSE: -4
    }[status]


def train(policy, env, gamma=1.0, log_interval=1000):
    """Train policy gradient."""
    optimizer = optim.Adam(policy.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, step_size=10000, gamma=0.9)
    running_reward = 0
    # inv_move = []
    for i_episode in count(1):
        saved_rewards = []
        saved_logprobs = []
        state = env.reset()
        done = False
        while not done:
            action, logprob = select_action(policy, state)
            state, status, done = env.play_against_random(action)
            if status=="inv":
                print('no')
            reward = get_reward(status)
            saved_logprobs.append(logprob)
            saved_rewards.append(reward)

        R = compute_returns(saved_rewards)[0]
        running_reward += R

        finish_episode(saved_rewards, saved_logprobs, gamma)

        if i_episode % log_interval == 0:
            print('Episode {}\tAverage return: {:.2f}'.format(
                i_episode,
                running_reward / log_interval))
            print(np.argmax(first_move_distr(policy, env)))
            win, lose, tie = rate(env, policy)
            print('win:', win)
            print('lose:', lose)
            print('tie:', tie)
            running_reward = 0
            torch.save(policy.state_dict(),
                       "test6/policy-%d.pkl" % i_episode)

        if i_episode % 1 == 0:  # batch_size
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()


def first_move_distr(policy, env):
    """Display the distribution of first moves."""
    state = env.reset()
    state = torch.from_numpy(state).long().unsqueeze(0)
    state = torch.zeros(3, 9).scatter_(0, state, 1).view(1, 27)
    pr = policy(Variable(state))
    return pr.data


def load_weights(policy, episode):
    """Load saved weights"""
    weights = torch.load("ttt/policy-%d.pkl" % episode)
    policy.load_state_dict(weights)


def baby_play(env, policy):
    action, logp = select_action(policy, env.grid)
    env.step(action)
    env.render()


def me_play(env, action):
    _,status,_=env.step(action)
    print(status)
    env.render()


def rate(env, policy):
    win = 0
    lose = 0
    tie = 0
    for session in range(100):
        state = env.reset()
        done = False
        status = env.STATUS_VALID_MOVE
        while not done:
            action, logprob = select_action(policy, state)
            state, status, done = env.play_against_random(action)
        if status == env.STATUS_WIN:
            win += 1
        if status == env.STATUS_LOSE:
            lose += 1
        if status == env.STATUS_TIE:
            tie += 1
    return win, lose, tie


if __name__ == '__main__':
    import sys

    policy = Policy()
    env = Environment()

    if len(sys.argv) == 1:
        # `python tictactoe.py` to train the agent
        train(policy, env)
    else:
        # `python tictactoe.py <ep>` to print the first move distribution
        # using weightt checkpoint at episode int(<ep>)
        ep = int(sys.argv[1])
        load_weights(policy, ep)
        print(first_move_distr(policy, env))
        print(np.argmax(first_move_distr(policy, env)))
