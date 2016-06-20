import logging

import numpy as np

import analysis
import creation
import plots
import randomwalk
import run
from mpi4py import MPI


def sim_2d_onlat(grid_size, tube_length, num_tubes, orientation, timesteps, save_loc_data,
                 quiet, save_loc_plots, save_dir, k_convergence_tolerance, begin_cov_check,
                 k_conv_error_buffer, plot_save_dir):
    walker_data_save_dir = save_dir + "/walker_locations"
    walker_plot_save_dir = save_dir + "/walker_plots"

    logging.info("Setting up grid and tubes")
    grid = creation.Grid2D_onlat(grid_size, tube_length, num_tubes, orientation)
    plots.plot_two_d_random_walk_setup(grid.tube_coords, grid.size, quiet, plot_save_dir)
    fill_fract = analysis.filling_fraction(grid.tube_coords, grid.size)
    logging.info("Filling fraction is %.2f" % fill_fract)

    grid_range = [[0, grid.size], [0, grid.size]]
    bins = grid.size
    H = np.zeros((grid.size, grid.size))

    i = 0
    k_list = []
    k_convergence_err_list = []
    k_convergence_err = 1.0

    while k_convergence_err > k_convergence_tolerance:
        # for i in range(num_walkers):

        # run hot walker
        # logging.info("Start hot walker %d" % (i+1))
        walker = randomwalk.runrandomwalk_2d_onlat(grid, timesteps, 'hot')
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'hot')
        if i == 0 & save_loc_plots == False:  # always save one example trajectory plot
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'hot', quiet, i + 1, plot_save_dir)
        elif save_loc_plots:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'hot', quiet, i + 1, walker_plot_save_dir)
        H_temp, xedges, yedges = plots.histogram_walker_2d_onlat(walker, grid_range, 'hot', bins)
        H += H_temp

        # run cold walker
        # logging.info("Start cold walker %d" % (i+1))
        walker = randomwalk.runrandomwalk_2d_onlat(grid, timesteps, 'cold')
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'cold')
        if i == 0 & save_loc_plots == False:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'cold', quiet, i + 1, plot_save_dir)
        elif save_loc_plots:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'cold', quiet, i + 1, walker_plot_save_dir)
        H_temp, xedges, yedges = plots.histogram_walker_2d_onlat(walker, grid_range, 'cold', bins)
        H -= H_temp

        i += 1

        dt_dx, heat_flux, dt_dx_err, k, k_err, r2 = analysis.check_convergence_2d_onlat(H, i * 2, grid.size, timesteps)
        k_list.append(k)
        logging.info("%d: R squared: %.4f, k: %.4E" % (i, r2, k))
        if i > begin_cov_check:
            k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
            k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
            k_convergence_err_list.append(k_convergence_err)
            logging.info("k: %.4E" % k_convergence_val)
            logging.info("k error: %.4E" % k_convergence_err)

    logging.info("Simulation has converged with %d total walkers" % (i * 2))
    logging.info("Finished random walks")
    plots.plot_k_convergence(k_list, quiet, plot_save_dir)
    plots.plot_k_convergence_err(k_convergence_err_list, quiet, plot_save_dir, begin_cov_check)
    temp_profile = plots.plot_histogram_walkers_2d_onlat(timesteps, H, xedges, yedges, quiet, plot_save_dir)
    temp_gradient_x = plots.plot_temp_gradient_2d_onlat(temp_profile, xedges, yedges, quiet,
                                                        plot_save_dir, gradient_cutoff=2)
    gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile, quiet, plot_save_dir)
    # plots.plot_check_gradient_noise_floor(temp_gradient_x, quiet, plot_save_dir)
    analysis.final_conductivity_2d_onlat(i * 2, grid.size, timesteps, gradient_avg, gradient_std,
                                         k_convergence_err, num_tubes, save_dir, k_convergence_val, gradient_cutoff=2)
    logging.info("Complete")


def sim_2d_onlat_MPI(grid_size, tube_length, num_tubes, orientation, timesteps, save_loc_data,
                     quiet, save_loc_plots, save_dir, k_convergence_tolerance, begin_cov_check,
                     k_conv_error_buffer, plot_save_dir, rank, size):
    comm = MPI.COMM_WORLD

    walker_data_save_dir = save_dir + "/walker_locations"
    walker_plot_save_dir = save_dir + "/walker_plots"

    if rank == 0:
        logging.info("Setting up grid and tubes")
        grid = creation.Grid2D_onlat(grid_size, tube_length, num_tubes, orientation)
        plots.plot_two_d_random_walk_setup(grid.tube_coords, grid.size, quiet, plot_save_dir)
        fill_fract = analysis.filling_fraction(grid.tube_coords, grid.size)
        logging.info("Filling fraction is %.2f" % fill_fract)
        comm.Scatter(grid, root=0)

    comm.Gather(grid, root=0)
    grid_range = [[0, grid.size], [0, grid.size]]
    bins = grid.size
    H = np.zeros((grid.size, grid.size))

    i = 0
    k_list = []
    k_convergence_err_list = []
    k_convergence_err = 1.0

    while k_convergence_err > k_convergence_tolerance:
        # for i in range(num_walkers):

        # run hot walker
        # logging.info("Start hot walker %d" % (i+1))
        walker = randomwalk.runrandomwalk_2d_onlat(grid, timesteps, 'hot')
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'hot')
        if i == 0 & save_loc_plots == False:  # always save one example trajectory plot
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'hot', quiet, i + 1, plot_save_dir)
        elif save_loc_plots:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'hot', quiet, i + 1, walker_plot_save_dir)
        H_temp, xedges, yedges = plots.histogram_walker_2d_onlat(walker, grid_range, 'hot', bins)
        H += H_temp

        # run cold walker
        # logging.info("Start cold walker %d" % (i+1))
        walker = randomwalk.runrandomwalk_2d_onlat(grid, timesteps, 'cold')
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'cold')
        if i == 0 & save_loc_plots == False:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'cold', quiet, i + 1, plot_save_dir)
        elif save_loc_plots:
            plots.plot_walker_path_2d_onlat(walker, grid_size, 'cold', quiet, i + 1, walker_plot_save_dir)
        H_temp, xedges, yedges = plots.histogram_walker_2d_onlat(walker, grid_range, 'cold', bins)
        H -= H_temp

        i += 1

        dt_dx, heat_flux, dt_dx_err, k, k_err, r2 = analysis.check_convergence_2d_onlat(H, i * 2, grid.size, timesteps)
        k_list.append(k)
        logging.info("%d: R squared: %.4f, k: %.4E" % (i, r2, k))
        if i > begin_cov_check:
            k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
            k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
            k_convergence_err_list.append(k_convergence_err)
            logging.info("k: %.4E" % k_convergence_val)
            logging.info("k error: %.4E" % k_convergence_err)

    logging.info("Simulation has converged with %d total walkers" % (i * 2))
    logging.info("Finished random walks")
    plots.plot_k_convergence(k_list, quiet, plot_save_dir)
    plots.plot_k_convergence_err(k_convergence_err_list, quiet, plot_save_dir, begin_cov_check)
    temp_profile = plots.plot_histogram_walkers_2d_onlat(timesteps, H, xedges, yedges, quiet, plot_save_dir)
    temp_gradient_x = plots.plot_temp_gradient_2d_onlat(temp_profile, xedges, yedges, quiet,
                                                        plot_save_dir, gradient_cutoff=2)
    gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile, quiet, plot_save_dir)
    # plots.plot_check_gradient_noise_floor(temp_gradient_x, quiet, plot_save_dir)
    analysis.final_conductivity_2d_onlat(i * 2, grid.size, timesteps, gradient_avg, gradient_std,
                                         k_convergence_err, num_tubes, save_dir, k_convergence_val, gradient_cutoff=2)
    logging.info("Complete")
