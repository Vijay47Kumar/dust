# -*- coding: utf-8 -*-
"""
StationSim
Created on Tue Nov 20 15:25:27 2018
@author: medkmin
"""

# sspmm.py
'''
StationSim (aka Mike's model) converted into python.
'''

#%% INIT
import numpy as np
from scipy.spatial import cKDTree
import matplotlib.pyplot as plt

def error(text='Self created error.'):
    """
    A couple of issues with this:
    - Do we really mean to import inside the function?
    - Are we basically trying to take care of exception handling?
      If so, wouldn't it be better to just use Python's exception handling?
    - Also, I don't think we use this anyway?
    """
    from sys import exit
    print()
    exit(text)

#%% MODEL
class Agent:
    """
    A class representing a generic agent for the StationSim ABM.
    """
    def __init__(self, model, unique_id):
        """
        Initialise a new agent.

        Creates a new agent and gives it a randomly chosen entrance, exit, and
        desired speed. All agents start with active state 0 ('not started').
        Their initial location (** HOW IS LOCATION REPRESENTED?? **) is set
        to the location of the entrance that they are assigned to.

        :param model: a pointer to the station sim model that is creating this agent
        """
        # Required
        self.unique_id = unique_id
        self.active = 0  # 0 Not Started, 1 Active, 2 Finished
        model.pop_active += 1

        # Choose at random at which of the entrances the agent starts
        self.location = model.loc_entrances[np.random.randint(model.entrances)]
        self.location[1] += model.entrance_space * (np.random.uniform() - .5)
        self.loc_desire = model.loc_exits[np.random.randint(model.exits)]

        # Parameters
        # model.entrance_speed -> the rate at which agents enter
        # self.time_activate -> the time at which the agent should become active
        # time_activate is exponentially distributed based on entrance_speed
        self.time_activate = np.random.exponential(model.entrance_speed)
        # The maximum speed that this agent can travel at:
        self.speed_desire = max(np.random.normal(model.speed_desire_mean,
                                                 model.speed_desire_std), 2*model.speed_min)
        # A few speeds to check; used if a step at the max speed would cause a collision
        self.speeds = np.arange(self.speed_desire, model.speed_min, -model.speed_step)
        if model.do_save:
            self.history_loc = []
        self.time_expected = None
        self.time_start = None

    def step(self, model):
        """
        Iterate the agent. If they are inactive then it checks to see if they
        should become active. If they are active then then move (see
        self.move()) and, possibly, leave the model (see exit_query())).
        """
        if self.active == 0:
            self.activate(model)
        elif self.active == 1:
            self.move(model)
            self.exit_query(model)
            self.save(model)

    def activate(self, model):
        """
        Test whether an agent should become active. This happens when the model
        time is greater than the agent's activate time.
        """
        if not self.active and model.time_id > self.time_activate:
            self.active = 1
            self.time_start = model.time_id
            self.time_expected = np.linalg.norm(self.location - self.loc_desire) / self.speed_desire

    @staticmethod
    def is_within_bounds(boundaries, new_location):
        """
        Check if new location is within the bounds of the model.
        :param boundaries      The boundaries of the model
        :param new_location    The proposed location for the agent
        :return                Is new location within boundaries, boolean
        """
        within0 = all(boundaries[0] <= new_location)
        within1 = all(boundaries[1] <= new_location)
        return within0 and within1

    def move(self, model):
        """
        Move the agent towards their destination. If the way is clear then the
        agent moves the maximum distance they can given their maximum possible
        speed (self.speed_desire). If not, then they iteratively test smaller
        and smaller distances until they find one that they can travel to
        without causing a colision with another agent.
        """
        for speed in self.speeds:
            # Direct
            new_location = Agent.lerp(self.loc_desire, self.location, speed)
            if not Agent.collision(model, new_location):
                break
            elif speed == self.speeds[-1]:
                # Wiggle
                # Why 1+1?
                new_location = self.location + np.random.randint(-1, 1+1, 2)
        # Rebound
        if not self.is_within_bounds(model.boundaries, new_location):
            new_location = np.clip(new_location, model.boundaries[0], model.boundaries[1])
        # Move
        self.location = new_location

    @classmethod
    def collision(cls, model, new_location):
        """
        Detects whether a move to the new_location will cause a collision
        (either with the model boundary or another agent).
        """
        within_bounds = all(model.boundaries[0] <= new_location) and all(new_location <= model.boundaries[1])
        if not within_bounds:
            collide = True
        elif Agent.neighbourhood(model, new_location):
            collide = True
        else:
            collide = False
        return collide

    @classmethod
    def neighbourhood(cls, model, new_location, do_kd_tree=True):
        """
        XXXX WHAT DOES THIS DO??

         :param model:        the model that this agent is part of
         :param new_location: the proposed new location that the agent will move to
                         (a XXXX - what kind of object/data is the location?)
         :param do_kd_tree    whether to use a spatial index (kd_tree) (default true)
        """
        neighbours = False
        neighbouring_agents = model.tree.query_ball_point(new_location, model.separation)
        for neighbouring_agent in neighbouring_agents:
            agent = model.agents[neighbouring_agent]
            if agent.active == 1 and new_location[0] <= agent.location[0]:
                neighbours = True
                break
        return neighbours

    @classmethod
    def lerp(cls, loc1, loc2, speed):
        """
        lerp - linear extrapolation
        Find the new position of after moving 'speed' distance from loc2 towards loc1.
        :param loc1: desired location
        :param loc2: current location
        :param speed: distance that can be covered in an iteration
        :return: The new location
        """
        distance = np.linalg.norm(loc1 - loc2)
        loc = loc2 + speed * (loc1 - loc2) / distance
        return loc

    def exit_query(self, model):
        """
        Determine whether the agent should leave the model and, if so,
        remove them. Otherwise do nothing.
        """
        if np.linalg.norm(self.location - self.loc_desire) < model.exit_space:
            self.active = 2
            model.pop_active -= 1
            model.pop_finished += 1
            if model.do_save:
                time_delta = model.time_id - self.time_start
                model.time_taken.append(time_delta)
                time_delta -= self.time_expected
                model.time_delayed.append(time_delta)

    def save(self, model):
        """
        Save agent location.
        """
        if model.do_save:
            self.history_loc.append(self.location)

class Model:
    """
    A class to represent the StationSim model.
    """
    def __init__(self, params):
        """
        Create a new model, reading parameters from a dictionary.
        XXXX Need to document the required parameters.
        """
        self.params = params
        # There are a lot of required attributes here that we hope are in params
        # Perhaps we should have a way to ensure we get what we require?
        # Also, consider using **kwargs
        [setattr(self, key, value) for key, value in params.items()]
        # Average number of speeds to check
        self.speed_step = (self.speed_desire_mean - self.speed_min) / 3
        # Batch Details
        self.time_id = 0
        self.step_id = 0
        if self.do_save:
            self.time_taken = []
            self.time_delayed = []
        # Model Parameters
        self.boundaries = np.array([[0, 0], [self.width, self.height]])
        self.pop_active = 0
        self.pop_finished = 0
        # Initialise
        self.initialise_gates()
        self.agents = [Agent(self, unique_id) for unique_id in range(self.pop_total)]

    def step(self):
        """
        Iterate model forward one step.
        """
        if self.pop_finished < self.pop_total and self.step:
            self.kdtree_build()
            [agent.step(self) for agent in self.agents]
        self.time_id += 1
        self.step_id += 1

    def initialise_gates(self):
        """
        Initialise the locations of the entrances and exits.
        """
        self.loc_entrances = self.initialise_gates_generic(self.entrances, 0)
        self.loc_exits = self.initialise_gates_generic(self.exits, self.width)

    def initialise_gates_generic(self, n_gates, x):
        """
        General method for initialising gates.
        Note: This method relies on a lot of class attributes, many of which are
        not explicitly required in the init method - perhaps we should be
        careful of this?
        """
        gates = np.zeros((n_gates, 2))
        gates[:, 0] = x
        if n_gates == 1:
            gates[0, 1] = self.height / 2
        else:
            gates[:, 1] = np.linspace(self.height / 4, 3 * self.height / 4,
                                      n_gates)
        return gates

    def kdtree_build(self):
        """
        Build kdtree for the model.
        """
        state = self.agents2state(do_ravel=False)
        self.tree = cKDTree(state)

    def agents2state(self, do_ravel=True):
        """
        Convert list of agents in model to state vector.
        """
        state = [agent.location for agent in self.agents]
        state = np.ravel(state) if do_ravel else np.array(state)
        return state

    def state2agents(self, state):
        """
        Use state vector to set agent locations.
        """
        for i in range(len(self.agents)):
            self.agents[i].location = state[2 * i:2 * i + 2]

    def batch(self):
        """
        Run the model.
        """
        print("Starting batch mode with following parameters:")
        print('\tParameter\tValue')
        for k, v in self.params.items():
            print('\t{0}:\t{1}'.format(k, v))
        print('')
        for i in range(self.batch_iterations):
            self.step()
            if i % 100 == 0:
                print("\tIterations: ", i)
            if self.do_ani:
                self.ani()
            if self.pop_finished == self.pop_total:
                print('Everyone made it!')
                break
        print("Finished at iteration", i)
        if self.do_save:
            self.save_stats()
            self.save_plot()

    def ani(self):
        plt.figure(1)
        plt.clf()
        for agent in self.agents:
            if agent.active == 1:
                plt.plot(*agent.location, '.k')#, markersize=4)
        plt.axis(np.ravel(self.boundaries, 'F'))
        plt.xlabel('Corridor Width')
        plt.ylabel('Corridor Height')
        plt.pause(1 / 30)
        return

    def save_ani(self):
        return

    def save_plot(self):
        """
        Produce plots for model.
        """
        self.plot_trails()
        self.plot_agent_times()

    def plot_trails(self):
        """
        Produce a plot of the trails of each agent in the 2-d corridor.
        """
        # Trails
        plt.figure()
        for agent in self.agents:
            if agent.active == 0:
                colour = 'r'
            elif agent.active == 1:
                colour = 'b'
            else:
                colour = 'm'
            locs = np.array(agent.history_loc).T
            plt.plot(locs[0], locs[1], color=colour, linewidth=.5)
        plt.axis(np.ravel(self.boundaries, 'F'))
        plt.xlabel('Corridor Width')
        plt.ylabel('Corridor Height')
        plt.legend(['Agent trails'])
        plt.show()

    def plot_agent_times(self):
        """
        Produce a plot of the time taken by each agent, and the delay of each
        agent.
        """
        # Time Taken, Delay Amount
        plt.figure()
        plt.hist(self.time_taken, alpha=.5, label='Time taken')
        plt.hist(self.time_delayed, alpha=.5, label='Time delay')
        plt.xlabel('Time')
        plt.ylabel('Number of Agents')
        plt.legend()
        plt.show()

    def save_stats(self):
        """
        Print model run stats to console.
        """
        print()
        print('Stats:')
        print('Finish Time: ' + str(self.time_id))
        print('Active / Finished / Total agents: ' +
              str(self.pop_active) + '/' + str(self.pop_finished) +
              '/' + str(self.pop_total))
        print('Average time taken: ' + str(np.mean(self.time_taken)) + 's')

    def __repr__(self):
        """Print this model's ID and its memory location"""
        return "StationSim [{}]".format(hex(id(self)))

    @classmethod
    def run_defaultmodel(cls):
        """
        Run a model with some common parameters. Mostly used for testing.
        """
        np.random.seed(42)
        model_params = {
            'width': 200,
            'height': 100,
            'pop_total': 700,
            'entrances': 3,
            'entrance_space': 2,
            'entrance_speed': .1,
            'exits': 2,
            'exit_space': 1,
            'speed_min': .1,
            'speed_desire_mean': 1,
            'speed_desire_std': 1,
            'separation': 2,
            'batch_iterations': 900,
            'do_save': True,
            'do_ani': False
        }
        # Run the model
        Model(model_params).batch()


# If this is called from the command line then run a default model.
if __name__ == '__main__':
    Model.run_defaultmodel()
