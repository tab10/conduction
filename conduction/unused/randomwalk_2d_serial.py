from __future__ import division
import logging
import numpy as np
import time
from mpi4py import MPI

from conduction import creation_2d
from conduction import plots
from conduction import rules_2d
from conduction import analysis


def serial_method(grid_size, tube_length, tube_radius, num_tubes, orientation, tot_time, quiet, plot_save_dir,
                  gen_plots, kapitza, prob_m_cn, tot_walkers, printout_inc, k_conv_error_buffer, disable_func):
    def histogram_walker_list(hot_walker_master, cold_walker_master):
        H = np.zeros((grid.size + 1, grid.size + 1))  # resets H every time function is called, IMPORTANT
        for i in range(len(hot_walker_master)):
            hot_temp = hot_walker_master[i]
            H[hot_temp.pos[-1][0], hot_temp.pos[-1][1]] += 1

            cold_temp = cold_walker_master[i]
            H[cold_temp.pos[-1][0], cold_temp.pos[-1][1]] -= 1
        # DEBUG, sum should be 0
        # print np.sum(H), np.max(H), np.min(H)
        return H

    grid = creation_2d.Grid2D_onlat(grid_size, tube_length, num_tubes, orientation, tube_radius, False, plot_save_dir,
                                    disable_func)
    if gen_plots:
        plots.plot_two_d_random_walk_setup(grid, quiet, plot_save_dir)
        # plots.plot_check_array_2d(grid, quiet, plot_save_dir, gen_plots)

    grid_range = [[0, grid.size + 1], [0, grid.size + 1]]
    bins = grid.size + 1

    start = time.clock()

    # these will hold the walker objects, need to access walker.pos for the positions
    hot_walker_master = []
    cold_walker_master = []
    k_list = []
    k_err_list = []
    dt_dx_list = []
    heat_flux_list = []
    timestep_list = []  # x axis for plots
    xedges = list(range(0, bins))
    yedges = list(range(0, bins))
    start_k_err_check = tot_time / 2

    # d_add - how often to add a hot/cold walker pair
    d_add = tot_time / (tot_walkers / 2.0)  # as a float
    if d_add.is_integer() and d_add >= 1:
        d_add = int(tot_time / (tot_walkers / 2.0))
        walker_frac_trigger = 0  # add a pair every d_add timesteps
    elif d_add < 1:  # this is a fractional number < 1, implies more than 1 walker pair should be added every timestep
        d_add = int(1.0 / d_add)
        walker_frac_trigger = 1
    else:  # change num_walkers or timesteps
        logging.error('Choose tot_time / (tot_walkers / 2.0) so that it is integer or less than 1')
        raise SystemExit
    if walker_frac_trigger == 1:
        logging.info('Adding %d hot/cold walker pair(s) every timestep, this might not converge' % d_add)
    elif walker_frac_trigger == 0:
        logging.info('Adding 1 hot/cold walker pair(s) every %d timesteps' % d_add)

    for i in range(tot_time):
        if (i % printout_inc) == 0 and (i >= (2 * printout_inc)):
            cur_num_walkers = len(hot_walker_master) * 2
            Htemp = histogram_walker_list(hot_walker_master, cold_walker_master)
            dt_dx, heat_flux, dt_dx_err, k, k_err, r2 = analysis.check_convergence_2d_onlat(Htemp, cur_num_walkers,
                                                                                            grid.size, i)
            k_list.append(k)
            dt_dx_list.append(dt_dx)
            heat_flux_list.append(heat_flux)
            timestep_list.append(i)
            if i >= start_k_err_check:
                k_err = np.std(k_list[-k_conv_error_buffer:], ddof=1)
                k_err_list.append(k_err)
                logging.info("Timestep: %d, %d walkers, R2: %.4f, k: %.4E, k err: %.4E, heat flux: %.4E, dT(x)/dx: %.4E"
                             % (i, cur_num_walkers, r2, k, k_err, heat_flux, dt_dx))
            else:
                logging.info("Timestep: %d, %d walkers, R2: %.4f, k: %.4E, heat flux: %.4E, dT(x)/dx: %.4E"
                             % (i, cur_num_walkers, r2, k, heat_flux, dt_dx))
        if walker_frac_trigger == 0:
            if (i % d_add) == 0:
                trigger = 1
                # let's add the 2 new walkers
                hot_walker_temp = creation_2d.Walker2D_onlat(grid.size, 'hot')
                cold_walker_temp = creation_2d.Walker2D_onlat(grid.size, 'cold')
                hot_walker_master.append(hot_walker_temp)
                cold_walker_master.append(cold_walker_temp)
            else:
                trigger = 0
        elif walker_frac_trigger == 1:
            trigger = d_add  # trigger never 0 in this case
            # let's add the 2 new walkers, several times
            for k in range(d_add):
                hot_walker_temp = creation_2d.Walker2D_onlat(grid.size, 'hot')
                cold_walker_temp = creation_2d.Walker2D_onlat(grid.size, 'cold')
                hot_walker_master.append(hot_walker_temp)
                cold_walker_master.append(cold_walker_temp)
        # let's update all the positions of the activated walkers
        for j in range(len(hot_walker_master) - trigger):  # except the new ones
            hot_temp = hot_walker_master[j]
            current_hot_updated = rules_2d.apply_moves_2d(hot_temp, kapitza, grid, prob_m_cn, True)
            current_hot_updated.erase_prev_pos()
            hot_walker_master[j] = current_hot_updated

            cold_temp = cold_walker_master[j]
            current_cold_updated = rules_2d.apply_moves_2d(cold_temp, kapitza, grid, prob_m_cn, True)
            current_cold_updated.erase_prev_pos()
            cold_walker_master[j] = current_cold_updated

    # let's histogram everything
    logging.info('Finished random walks, histogramming...')

    H = histogram_walker_list(hot_walker_master, cold_walker_master)

    dt_dx, heat_flux, dt_dx_err, k, k_err, r2 = analysis.check_convergence_2d_onlat(H, tot_walkers,
                                                                                    grid.size, tot_time)
    logging.info("%d walkers: R squared: %.4f, k: %.4E, heat flux: %.4E, dT(x)/dx: %.4E" % (tot_walkers, r2, k,
                                                                                            heat_flux, dt_dx))

    end = time.clock()
    logging.info("Constant flux simulation has completed")
    logging.info("Serial simulation time was %.4f s" % (end - start))

    temp_profile = plots.plot_colormap_2d(grid, H, quiet, plot_save_dir, gen_plots)
    if gen_plots:
        plots.plot_k_convergence(k_list, quiet, plot_save_dir, timestep_list)
        plots.plot_k_convergence_err(k_list, quiet, plot_save_dir, start_k_err_check, timestep_list)
        plots.plot_dt_dx(dt_dx_list, quiet, plot_save_dir, timestep_list)
        plots.plot_heat_flux(heat_flux_list, quiet, plot_save_dir, timestep_list)
        temp_gradient_x = plots.plot_temp_gradient_2d_onlat(grid, temp_profile, xedges, yedges, quiet,
                                                            plot_save_dir, gradient_cutoff=0)
        gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile, grid_size, quiet, plot_save_dir,
                                                            gen_plots)
    logging.info("Complete")
